"""Event bus for pub/sub messaging patterns."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, Optional
from uuid import uuid4

from .client import MessageQueueClient
from common.logging import get_logger

LOGGER = get_logger(__name__)


@dataclass
class Event:
    """Event message."""

    event_type: str
    data: Dict[str, Any]
    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    source: Optional[str] = None
    correlation_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "correlation_id": self.correlation_id,
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Event:
        """Create event from dictionary."""
        return cls(
            event_id=data["event_id"],
            event_type=data["event_type"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            source=data.get("source"),
            correlation_id=data.get("correlation_id"),
            data=data["data"],
        )


class EventBus:
    """Event bus for publishing and subscribing to events.

    Example:
        # Publisher
        bus = EventBus(rabbitmq_url, source="fabrication-service")
        bus.publish("fabrication.print.started", {"job_id": "123"})

        # Subscriber
        def handle_print_started(event: Event):
            print(f"Print started: {event.data['job_id']}")

        bus.subscribe("fabrication.print.started", handle_print_started)
        bus.start_consuming()
    """

    def __init__(
        self,
        rabbitmq_url: str,
        source: Optional[str] = None,
        exchange: str = "kitty.events",
    ):
        """Initialize event bus.

        Args:
            rabbitmq_url: RabbitMQ connection URL
            source: Event source identifier (e.g., "fabrication-service")
            exchange: Exchange name for events
        """
        self.client = MessageQueueClient(rabbitmq_url, connection_name=f"eventbus-{source or 'unknown'}")
        self.source = source
        self.exchange = exchange
        self._handlers: Dict[str, list[Callable]] = {}

    def connect(self) -> None:
        """Connect to message queue."""
        self.client.connect()

    def disconnect(self) -> None:
        """Disconnect from message queue."""
        self.client.disconnect()

    def publish(
        self,
        event_type: str,
        data: Dict[str, Any],
        correlation_id: Optional[str] = None,
    ) -> Event:
        """Publish event.

        Args:
            event_type: Event type (e.g., "fabrication.print.started")
            data: Event data
            correlation_id: Optional correlation ID for request tracing

        Returns:
            Published event
        """
        event = Event(
            event_type=event_type,
            data=data,
            source=self.source,
            correlation_id=correlation_id,
        )

        # Use event_type as routing key for topic exchange
        self.client.publish_event(
            routing_key=event_type,
            event_data=event.to_dict(),
            event_type=event_type,
        )

        LOGGER.info(
            "Published event",
            event_type=event_type,
            event_id=event.event_id,
            source=self.source,
        )

        return event

    def subscribe(
        self,
        event_pattern: str,
        handler: Callable[[Event], None],
        queue_name: Optional[str] = None,
    ) -> None:
        """Subscribe to events matching pattern.

        Args:
            event_pattern: Event pattern (supports wildcards: * and #)
                Examples: "fabrication.*", "fabrication.print.#"
            handler: Event handler function
            queue_name: Queue name (auto-generated if not provided)
        """
        if queue_name is None:
            queue_name = f"events.{self.source or 'subscriber'}.{event_pattern.replace('#', 'all').replace('*', 'any')}"

        # Declare queue and bind to exchange
        self.client.declare_queue(queue_name, durable=True)
        self.client.bind_queue(
            queue_name=queue_name,
            exchange_name=self.exchange,
            routing_key=event_pattern,
        )

        # Store handler
        if queue_name not in self._handlers:
            self._handlers[queue_name] = []
        self._handlers[queue_name].append(handler)

        LOGGER.info(
            "Subscribed to events",
            pattern=event_pattern,
            queue=queue_name,
            handler=handler.__name__,
        )

    def start_consuming(self, queue_name: Optional[str] = None) -> None:
        """Start consuming events.

        Args:
            queue_name: Queue to consume (consumes all subscribed queues if None)
        """
        if queue_name:
            self._consume_queue(queue_name)
        else:
            # Consume all subscribed queues
            for q_name in self._handlers.keys():
                self._consume_queue(q_name)

    def _consume_queue(self, queue_name: str) -> None:
        """Consume events from queue.

        Args:
            queue_name: Queue name
        """
        def callback(ch, method, properties, body):
            try:
                message = json.loads(body.decode("utf-8"))
                event = Event.from_dict(message)

                # Call all registered handlers
                for handler in self._handlers.get(queue_name, []):
                    try:
                        handler(event)
                    except Exception as e:
                        LOGGER.error(
                            "Event handler failed",
                            event_type=event.event_type,
                            event_id=event.event_id,
                            handler=handler.__name__,
                            error=str(e),
                            exc_info=True,
                        )

                # Acknowledge message
                ch.basic_ack(delivery_tag=method.delivery_tag)

            except Exception as e:
                LOGGER.error(
                    "Failed to process event",
                    queue=queue_name,
                    error=str(e),
                    exc_info=True,
                )
                # Reject and requeue
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

        self.client.consume(queue_name, callback, auto_ack=False, prefetch_count=10)

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
