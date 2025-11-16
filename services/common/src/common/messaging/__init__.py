"""Message queue client library for KITT services.

Provides pub/sub, work queues, and RPC patterns using RabbitMQ.
"""

from .client import MessageQueueClient
from .events import Event, EventBus
from .tasks import Task, TaskQueue
from .rpc import RPCClient, RPCServer

__all__ = [
    "MessageQueueClient",
    "Event",
    "EventBus",
    "Task",
    "TaskQueue",
    "RPCClient",
    "RPCServer",
]
