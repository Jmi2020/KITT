"""RabbitMQ message queue client."""

from __future__ import annotations

import json
import time
from typing import Any, Callable, Dict, Optional
from uuid import uuid4

import pika
from pika.adapters.blocking_connection import BlockingChannel
from pika.exceptions import AMQPConnectionError

from common.logging import get_logger

LOGGER = get_logger(__name__)


class MessageQueueClient:
    """RabbitMQ client for KITT services.

    Provides connection management, publishing, and consuming capabilities
    with automatic reconnection and error handling.

    Example:
        client = MessageQueueClient("amqp://user:pass@localhost:5672/")
        client.connect()

        # Publish event
        client.publish_event("fabrication.print.started", {"job_id": "123"})

        # Consume messages
        def callback(ch, method, properties, body):
            print(f"Received: {body}")

        client.consume("my.queue", callback)
    """

    def __init__(
        self,
        url: str,
        connection_name: Optional[str] = None,
        heartbeat: int = 60,
        blocked_connection_timeout: int = 300,
    ):
        """Initialize message queue client.

        Args:
            url: RabbitMQ connection URL (amqp://user:pass@host:port/vhost)
            connection_name: Client connection name for management UI
            heartbeat: Heartbeat interval in seconds
            blocked_connection_timeout: Timeout for blocked connections
        """
        self.url = url
        self.connection_name = connection_name or f"kitty-{uuid4().hex[:8]}"
        self.heartbeat = heartbeat
        self.blocked_connection_timeout = blocked_connection_timeout

        self._connection: Optional[pika.BlockingConnection] = None
        self._channel: Optional[BlockingChannel] = None
        self._is_connected = False

    def connect(self) -> None:
        """Establish connection to RabbitMQ server.

        Raises:
            AMQPConnectionError: If connection fails
        """
        try:
            parameters = pika.URLParameters(self.url)
            parameters.client_properties = {"connection_name": self.connection_name}
            parameters.heartbeat = self.heartbeat
            parameters.blocked_connection_timeout = self.blocked_connection_timeout

            self._connection = pika.BlockingConnection(parameters)
            self._channel = self._connection.channel()
            self._is_connected = True

            LOGGER.info(
                "Connected to message queue",
                connection_name=self.connection_name,
                url=self.url.split("@")[-1],  # Hide credentials in logs
            )

        except AMQPConnectionError as e:
            LOGGER.error(
                "Failed to connect to message queue",
                error=str(e),
                url=self.url.split("@")[-1],
            )
            raise

    def disconnect(self) -> None:
        """Close connection to RabbitMQ server."""
        if self._connection and self._connection.is_open:
            self._connection.close()
            self._is_connected = False
            LOGGER.info("Disconnected from message queue", connection_name=self.connection_name)

    def _ensure_connected(self) -> None:
        """Ensure connection is active, reconnect if needed."""
        if not self._is_connected or not self._connection or not self._connection.is_open:
            LOGGER.warning("Connection lost, attempting to reconnect...")
            self.connect()

    # ========================================================================
    # Publishing
    # ========================================================================

    def publish(
        self,
        exchange: str,
        routing_key: str,
        message: Dict[str, Any],
        properties: Optional[pika.BasicProperties] = None,
        mandatory: bool = False,
    ) -> None:
        """Publish message to exchange.

        Args:
            exchange: Exchange name
            routing_key: Routing key for message routing
            message: Message payload (will be JSON-encoded)
            properties: Message properties (delivery mode, headers, etc.)
            mandatory: If True, message must be routable to a queue

        Raises:
            AMQPConnectionError: If connection fails during publish
        """
        self._ensure_connected()

        if properties is None:
            properties = pika.BasicProperties(
                delivery_mode=2,  # Persistent
                content_type="application/json",
            )

        body = json.dumps(message).encode("utf-8")

        try:
            self._channel.basic_publish(
                exchange=exchange,
                routing_key=routing_key,
                body=body,
                properties=properties,
                mandatory=mandatory,
            )

            LOGGER.debug(
                "Published message",
                exchange=exchange,
                routing_key=routing_key,
                size_bytes=len(body),
            )

        except Exception as e:
            LOGGER.error(
                "Failed to publish message",
                exchange=exchange,
                routing_key=routing_key,
                error=str(e),
            )
            raise

    def publish_event(
        self,
        routing_key: str,
        event_data: Dict[str, Any],
        event_type: Optional[str] = None,
    ) -> None:
        """Publish event to kitty.events exchange.

        Args:
            routing_key: Event routing key (e.g., "fabrication.print.started")
            event_data: Event payload
            event_type: Event type (defaults to routing_key)
        """
        event_type = event_type or routing_key

        message = {
            "event_id": str(uuid4()),
            "event_type": event_type,
            "timestamp": time.time(),
            "data": event_data,
        }

        properties = pika.BasicProperties(
            delivery_mode=2,
            content_type="application/json",
            headers={"event_type": event_type},
        )

        self.publish(
            exchange="kitty.events",
            routing_key=routing_key,
            message=message,
            properties=properties,
        )

    def publish_task(
        self,
        queue_name: str,
        task_data: Dict[str, Any],
        task_type: Optional[str] = None,
        priority: int = 5,
    ) -> str:
        """Publish task to work queue.

        Args:
            queue_name: Task queue name (e.g., "research", "cad")
            task_data: Task payload
            task_type: Task type identifier
            priority: Task priority (0-10, higher = more priority)

        Returns:
            Task ID
        """
        task_id = str(uuid4())
        task_type = task_type or queue_name

        message = {
            "task_id": task_id,
            "task_type": task_type,
            "timestamp": time.time(),
            "data": task_data,
        }

        properties = pika.BasicProperties(
            delivery_mode=2,
            content_type="application/json",
            priority=priority,
            headers={"task_type": task_type, "task_id": task_id},
        )

        self.publish(
            exchange="kitty.tasks",
            routing_key=queue_name,
            message=message,
            properties=properties,
        )

        return task_id

    # ========================================================================
    # Consuming
    # ========================================================================

    def consume(
        self,
        queue_name: str,
        callback: Callable,
        auto_ack: bool = False,
        prefetch_count: int = 1,
    ) -> None:
        """Start consuming messages from queue.

        Args:
            queue_name: Queue to consume from
            callback: Message handler function(ch, method, properties, body)
            auto_ack: Automatically acknowledge messages
            prefetch_count: Number of messages to prefetch (QoS)

        Note:
            This is a blocking operation. Use in a dedicated consumer thread/process.
        """
        self._ensure_connected()

        # Set QoS (prefetch count)
        self._channel.basic_qos(prefetch_count=prefetch_count)

        # Start consuming
        self._channel.basic_consume(
            queue=queue_name,
            on_message_callback=callback,
            auto_ack=auto_ack,
        )

        LOGGER.info("Starting consumer", queue=queue_name, prefetch_count=prefetch_count)

        try:
            self._channel.start_consuming()
        except KeyboardInterrupt:
            LOGGER.info("Consumer interrupted", queue=queue_name)
            self._channel.stop_consuming()

    def ack(self, delivery_tag: int) -> None:
        """Acknowledge message delivery.

        Args:
            delivery_tag: Message delivery tag from method
        """
        self._channel.basic_ack(delivery_tag=delivery_tag)

    def nack(self, delivery_tag: int, requeue: bool = True) -> None:
        """Negative acknowledge message (reject).

        Args:
            delivery_tag: Message delivery tag from method
            requeue: If True, message goes back to queue; if False, to DLX
        """
        self._channel.basic_nack(delivery_tag=delivery_tag, requeue=requeue)

    # ========================================================================
    # Queue/Exchange Management
    # ========================================================================

    def declare_queue(
        self,
        queue_name: str,
        durable: bool = True,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Declare queue.

        Args:
            queue_name: Queue name
            durable: Queue survives broker restart
            arguments: Additional queue arguments (x-max-length, etc.)
        """
        self._ensure_connected()

        self._channel.queue_declare(
            queue=queue_name,
            durable=durable,
            arguments=arguments or {},
        )

        LOGGER.debug("Declared queue", queue=queue_name, durable=durable)

    def declare_exchange(
        self,
        exchange_name: str,
        exchange_type: str = "topic",
        durable: bool = True,
    ) -> None:
        """Declare exchange.

        Args:
            exchange_name: Exchange name
            exchange_type: Exchange type (topic, direct, fanout, headers)
            durable: Exchange survives broker restart
        """
        self._ensure_connected()

        self._channel.exchange_declare(
            exchange=exchange_name,
            exchange_type=exchange_type,
            durable=durable,
        )

        LOGGER.debug("Declared exchange", exchange=exchange_name, type=exchange_type)

    def bind_queue(
        self,
        queue_name: str,
        exchange_name: str,
        routing_key: str = "",
    ) -> None:
        """Bind queue to exchange.

        Args:
            queue_name: Queue name
            exchange_name: Exchange name
            routing_key: Routing key pattern
        """
        self._ensure_connected()

        self._channel.queue_bind(
            queue=queue_name,
            exchange=exchange_name,
            routing_key=routing_key,
        )

        LOGGER.debug(
            "Bound queue to exchange",
            queue=queue_name,
            exchange=exchange_name,
            routing_key=routing_key,
        )

    # ========================================================================
    # Helpers
    # ========================================================================

    def get_queue_size(self, queue_name: str) -> int:
        """Get number of messages in queue.

        Args:
            queue_name: Queue name

        Returns:
            Message count
        """
        self._ensure_connected()

        method = self._channel.queue_declare(queue=queue_name, passive=True)
        return method.method.message_count

    def purge_queue(self, queue_name: str) -> None:
        """Delete all messages from queue.

        Args:
            queue_name: Queue name
        """
        self._ensure_connected()

        self._channel.queue_purge(queue=queue_name)
        LOGGER.warning("Purged queue", queue=queue_name)

    @property
    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self._is_connected and self._connection and self._connection.is_open

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
