"""Task queue for work distribution patterns."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Optional
from uuid import uuid4

from .client import MessageQueueClient
from common.logging import get_logger

LOGGER = get_logger(__name__)


class TaskStatus(Enum):
    """Task execution status."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class Task:
    """Task message."""

    task_type: str
    data: Dict[str, Any]
    task_id: str = field(default_factory=lambda: str(uuid4()))
    priority: int = 5  # 0-10 scale
    max_retries: int = 3
    retry_count: int = 0
    timeout_seconds: Optional[int] = None
    created_at: float = field(default_factory=time.time)
    status: TaskStatus = TaskStatus.PENDING

    def to_dict(self) -> Dict[str, Any]:
        """Convert task to dictionary."""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "data": self.data,
            "priority": self.priority,
            "max_retries": self.max_retries,
            "retry_count": self.retry_count,
            "timeout_seconds": self.timeout_seconds,
            "created_at": self.created_at,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Task:
        """Create task from dictionary."""
        return cls(
            task_id=data["task_id"],
            task_type=data["task_type"],
            data=data["data"],
            priority=data.get("priority", 5),
            max_retries=data.get("max_retries", 3),
            retry_count=data.get("retry_count", 0),
            timeout_seconds=data.get("timeout_seconds"),
            created_at=data.get("created_at", time.time()),
            status=TaskStatus(data.get("status", "pending")),
        )


class TaskQueue:
    """Task queue for distributing work to workers.

    Example:
        # Producer
        queue = TaskQueue(rabbitmq_url, queue_name="research.tasks")
        task_id = queue.submit("research_paper", {"query": "3D printing failures"})

        # Worker
        def process_research(task: Task):
            print(f"Researching: {task.data['query']}")
            return {"results": [...]}

        queue.register_handler("research_paper", process_research)
        queue.start_worker()
    """

    def __init__(
        self,
        rabbitmq_url: str,
        queue_name: str,
        exchange: str = "kitty.tasks",
    ):
        """Initialize task queue.

        Args:
            rabbitmq_url: RabbitMQ connection URL
            queue_name: Task queue name (e.g., "research.tasks")
            exchange: Exchange name for tasks
        """
        self.client = MessageQueueClient(rabbitmq_url, connection_name=f"taskqueue-{queue_name}")
        self.queue_name = queue_name
        self.exchange = exchange
        self._handlers: Dict[str, Callable] = {}

    def connect(self) -> None:
        """Connect to message queue."""
        self.client.connect()

        # Ensure queue exists with priority support
        self.client.declare_queue(
            self.queue_name,
            durable=True,
            arguments={
                "x-max-priority": 10,  # Enable priority queue
                "x-queue-type": "classic",
            },
        )

    def disconnect(self) -> None:
        """Disconnect from message queue."""
        self.client.disconnect()

    def submit(
        self,
        task_type: str,
        data: Dict[str, Any],
        priority: int = 5,
        max_retries: int = 3,
        timeout_seconds: Optional[int] = None,
    ) -> str:
        """Submit task to queue.

        Args:
            task_type: Task type identifier
            data: Task data
            priority: Task priority (0-10, higher = more priority)
            max_retries: Maximum retry attempts on failure
            timeout_seconds: Task timeout in seconds

        Returns:
            Task ID
        """
        task = Task(
            task_type=task_type,
            data=data,
            priority=priority,
            max_retries=max_retries,
            timeout_seconds=timeout_seconds,
        )

        task_id = self.client.publish_task(
            queue_name=self.queue_name.split(".")[-1],  # Extract routing key
            task_data=task.to_dict(),
            task_type=task_type,
            priority=priority,
        )

        LOGGER.info(
            "Submitted task",
            task_id=task_id,
            task_type=task_type,
            priority=priority,
            queue=self.queue_name,
        )

        return task_id

    def register_handler(
        self,
        task_type: str,
        handler: Callable[[Task], Any],
    ) -> None:
        """Register task handler.

        Args:
            task_type: Task type to handle
            handler: Task handler function (receives Task, returns result)
        """
        self._handlers[task_type] = handler

        LOGGER.info(
            "Registered task handler",
            task_type=task_type,
            handler=handler.__name__,
        )

    def start_worker(self, prefetch_count: int = 1) -> None:
        """Start worker to process tasks.

        Args:
            prefetch_count: Number of tasks to prefetch (parallelism level)
        """
        def callback(ch, method, properties, body):
            try:
                message = json.loads(body.decode("utf-8"))
                task = Task.from_dict(message)

                LOGGER.info(
                    "Processing task",
                    task_id=task.task_id,
                    task_type=task.task_type,
                    retry_count=task.retry_count,
                )

                # Find handler
                handler = self._handlers.get(task.task_type)
                if not handler:
                    LOGGER.error(
                        "No handler registered for task type",
                        task_type=task.task_type,
                        task_id=task.task_id,
                    )
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                    return

                # Execute task
                task.status = TaskStatus.PROCESSING
                start_time = time.time()

                try:
                    result = handler(task)
                    elapsed = time.time() - start_time

                    task.status = TaskStatus.COMPLETED

                    LOGGER.info(
                        "Task completed",
                        task_id=task.task_id,
                        task_type=task.task_type,
                        elapsed_seconds=round(elapsed, 2),
                    )

                    # Acknowledge message
                    ch.basic_ack(delivery_tag=method.delivery_tag)

                except Exception as e:
                    elapsed = time.time() - start_time

                    LOGGER.error(
                        "Task failed",
                        task_id=task.task_id,
                        task_type=task.task_type,
                        retry_count=task.retry_count,
                        max_retries=task.max_retries,
                        error=str(e),
                        elapsed_seconds=round(elapsed, 2),
                        exc_info=True,
                    )

                    # Retry logic
                    if task.retry_count < task.max_retries:
                        task.retry_count += 1
                        task.status = TaskStatus.RETRYING

                        # Requeue with exponential backoff (via retry queue)
                        LOGGER.info(
                            "Retrying task",
                            task_id=task.task_id,
                            retry_count=task.retry_count,
                            max_retries=task.max_retries,
                        )

                        # Nack with requeue=True for simple retry
                        # Or publish to retry queue with delay
                        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
                    else:
                        task.status = TaskStatus.FAILED

                        LOGGER.error(
                            "Task failed permanently",
                            task_id=task.task_id,
                            task_type=task.task_type,
                            retry_count=task.retry_count,
                        )

                        # Send to dead letter queue
                        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

            except Exception as e:
                LOGGER.error(
                    "Failed to process task message",
                    queue=self.queue_name,
                    error=str(e),
                    exc_info=True,
                )
                # Reject and requeue
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

        LOGGER.info("Starting task worker", queue=self.queue_name, prefetch_count=prefetch_count)

        self.client.consume(
            self.queue_name,
            callback,
            auto_ack=False,
            prefetch_count=prefetch_count,
        )

    def get_queue_size(self) -> int:
        """Get number of pending tasks in queue."""
        return self.client.get_queue_size(self.queue_name)

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
