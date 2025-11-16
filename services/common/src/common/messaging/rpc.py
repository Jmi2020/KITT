"""RPC (Request/Reply) messaging pattern."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Callable, Dict, Optional
from queue import Queue, Empty

import pika

from .client import MessageQueueClient
from common.logging import get_logger

LOGGER = get_logger(__name__)


class RPCClient:
    """RPC client for request/reply pattern.

    Example:
        client = RPCClient(rabbitmq_url)
        client.connect()

        result = client.call("rpc_queue", {"operation": "add", "a": 5, "b": 3})
        print(result)  # {"result": 8}
    """

    def __init__(self, rabbitmq_url: str):
        """Initialize RPC client.

        Args:
            rabbitmq_url: RabbitMQ connection URL
        """
        self.client = MessageQueueClient(rabbitmq_url, connection_name="rpc-client")
        self._responses: Dict[str, Any] = {}
        self._callback_queue: Optional[str] = None

    def connect(self) -> None:
        """Connect to message queue."""
        self.client.connect()

        # Declare exclusive callback queue
        result = self.client._channel.queue_declare(queue="", exclusive=True)
        self._callback_queue = result.method.queue

        # Start consuming responses
        self.client._channel.basic_consume(
            queue=self._callback_queue,
            on_message_callback=self._on_response,
            auto_ack=True,
        )

    def disconnect(self) -> None:
        """Disconnect from message queue."""
        self.client.disconnect()

    def _on_response(self, ch, method, properties, body):
        """Handle RPC response."""
        correlation_id = properties.correlation_id
        if correlation_id in self._responses:
            self._responses[correlation_id] = json.loads(body.decode("utf-8"))

    def call(
        self,
        queue_name: str,
        request: Dict[str, Any],
        timeout: int = 30,
    ) -> Any:
        """Make RPC call.

        Args:
            queue_name: RPC queue name
            request: Request payload
            timeout: Response timeout in seconds

        Returns:
            Response data

        Raises:
            TimeoutError: If no response received within timeout
        """
        correlation_id = str(uuid.uuid4())
        self._responses[correlation_id] = None

        # Publish request
        properties = pika.BasicProperties(
            reply_to=self._callback_queue,
            correlation_id=correlation_id,
            content_type="application/json",
        )

        self.client.publish(
            exchange="",
            routing_key=queue_name,
            message=request,
            properties=properties,
        )

        LOGGER.debug(
            "Sent RPC request",
            queue=queue_name,
            correlation_id=correlation_id,
        )

        # Wait for response
        start_time = time.time()
        while self._responses[correlation_id] is None:
            self.client._connection.process_data_events(time_limit=0.1)

            if time.time() - start_time > timeout:
                del self._responses[correlation_id]
                raise TimeoutError(f"RPC call to {queue_name} timed out after {timeout}s")

        response = self._responses.pop(correlation_id)

        LOGGER.debug(
            "Received RPC response",
            queue=queue_name,
            correlation_id=correlation_id,
        )

        return response

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()


class RPCServer:
    """RPC server for handling requests.

    Example:
        def add(request):
            return {"result": request["a"] + request["b"]}

        server = RPCServer(rabbitmq_url, "rpc_queue")
        server.register_handler(add)
        server.start()
    """

    def __init__(self, rabbitmq_url: str, queue_name: str):
        """Initialize RPC server.

        Args:
            rabbitmq_url: RabbitMQ connection URL
            queue_name: RPC queue name
        """
        self.client = MessageQueueClient(rabbitmq_url, connection_name=f"rpc-server-{queue_name}")
        self.queue_name = queue_name
        self._handler: Optional[Callable] = None

    def connect(self) -> None:
        """Connect to message queue."""
        self.client.connect()

        # Declare RPC queue
        self.client.declare_queue(self.queue_name, durable=True)

    def disconnect(self) -> None:
        """Disconnect from message queue."""
        self.client.disconnect()

    def register_handler(self, handler: Callable[[Dict[str, Any]], Any]) -> None:
        """Register RPC handler.

        Args:
            handler: Request handler function (receives request, returns response)
        """
        self._handler = handler
        LOGGER.info("Registered RPC handler", queue=self.queue_name, handler=handler.__name__)

    def start(self, prefetch_count: int = 1) -> None:
        """Start RPC server.

        Args:
            prefetch_count: Number of requests to process in parallel
        """
        if not self._handler:
            raise ValueError("No handler registered. Call register_handler() first.")

        def callback(ch, method, properties, body):
            try:
                request = json.loads(body.decode("utf-8"))

                LOGGER.debug(
                    "Received RPC request",
                    queue=self.queue_name,
                    correlation_id=properties.correlation_id,
                )

                # Process request
                response = self._handler(request)

                # Send response
                response_properties = pika.BasicProperties(
                    correlation_id=properties.correlation_id,
                    content_type="application/json",
                )

                ch.basic_publish(
                    exchange="",
                    routing_key=properties.reply_to,
                    body=json.dumps(response).encode("utf-8"),
                    properties=response_properties,
                )

                ch.basic_ack(delivery_tag=method.delivery_tag)

                LOGGER.debug(
                    "Sent RPC response",
                    queue=self.queue_name,
                    correlation_id=properties.correlation_id,
                )

            except Exception as e:
                LOGGER.error(
                    "RPC request processing failed",
                    queue=self.queue_name,
                    error=str(e),
                    exc_info=True,
                )
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

        LOGGER.info("Starting RPC server", queue=self.queue_name, prefetch_count=prefetch_count)

        self.client.consume(
            self.queue_name,
            callback,
            auto_ack=False,
            prefetch_count=prefetch_count,
        )

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
