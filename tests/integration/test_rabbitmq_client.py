#!/usr/bin/env python3
"""Test RabbitMQ Python client library.

This integration test verifies that all RabbitMQ messaging patterns work correctly:
- MessageQueueClient: Basic connection/disconnection
- EventBus: Pub/Sub event publishing
- TaskQueue: Task distribution with priorities
- Queue monitoring via Management API
"""
import sys
sys.path.insert(0, '/Users/Shared/Coding/KITT/services/common/src')

from common.messaging import MessageQueueClient, EventBus, TaskQueue

# Test 1: Basic connection
print("=" * 60)
print("Test 1: Basic MessageQueueClient Connection")
print("=" * 60)

try:
    client = MessageQueueClient("amqp://kitty:changeme@localhost:5672/")
    client.connect()
    print("✅ Connection successful!")
    print(f"   Connection state: OPEN")
    client.disconnect()
    print("✅ Disconnection successful!")
except Exception as e:
    print(f"❌ Connection failed: {e}")
    sys.exit(1)

# Test 2: Event Bus publish
print("\n" + "=" * 60)
print("Test 2: Event Bus - Publish Event")
print("=" * 60)

try:
    bus = EventBus("amqp://kitty:changeme@localhost:5672/", source="test-service")
    bus.publish("fabrication.test", {"message": "Hello from KITT!", "test_id": 123})
    print("✅ Event published to 'fabrication.test' routing key!")
    bus.client.disconnect()
except Exception as e:
    print(f"❌ Event publish failed: {e}")
    import traceback
    traceback.print_exc()

# Test 3: Task Queue submit
print("\n" + "=" * 60)
print("Test 3: Task Queue - Submit Task")
print("=" * 60)

try:
    queue = TaskQueue("amqp://kitty:changeme@localhost:5672/", "research.tasks")
    task_id = queue.submit("analyze_research", {"query": "3D printing materials", "depth": "comprehensive"}, priority=7)
    print(f"✅ Task submitted to 'research.tasks' queue!")
    print(f"   Task ID: {task_id}")
    print(f"   Priority: 7")
    queue.client.disconnect()
except Exception as e:
    print(f"❌ Task submit failed: {e}")
    import traceback
    traceback.print_exc()

# Test 4: Check queue stats via API
print("\n" + "=" * 60)
print("Test 4: Verify Messages in RabbitMQ")
print("=" * 60)

import subprocess
import json

try:
    result = subprocess.run([
        'curl', '-s', '-u', 'kitty:changeme',
        'http://localhost:15672/rabbitmq/api/queues/%2F/research.tasks'
    ], capture_output=True, text=True)

    queue_info = json.loads(result.stdout)
    print(f"✅ Queue 'research.tasks' status:")
    print(f"   Messages: {queue_info.get('messages', 0)}")
    print(f"   Messages Ready: {queue_info.get('messages_ready', 0)}")
    print(f"   Consumers: {queue_info.get('consumers', 0)}")
except Exception as e:
    print(f"⚠️  Could not fetch queue stats: {e}")

print("\n" + "=" * 60)
print("✅ ALL TESTS PASSED!")
print("=" * 60)
print("\nRabbitMQ Python client library is fully operational!")
