"""MQTT helpers used by services when publishing device commands or telemetry."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

import paho.mqtt.client as mqtt

from .config import settings

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class PublishOptions:
    """Options controlling publish behaviour."""

    qos: int = 1
    retain: bool = False


class MQTTClient:
    """Thin wrapper around paho to standardise configuration across services."""

    def __init__(self, client_id: Optional[str] = None) -> None:
        self._client = mqtt.Client(client_id=client_id, clean_session=True)
        if settings.mqtt_username and settings.mqtt_password:
            self._client.username_pw_set(settings.mqtt_username, settings.mqtt_password)

    def connect(self) -> None:
        LOGGER.info(
            "Connecting to MQTT broker",
            extra={"host": settings.mqtt_host, "port": settings.mqtt_port},
        )
        self._client.connect(settings.mqtt_host, settings.mqtt_port, keepalive=60)
        self._client.loop_start()

    def disconnect(self) -> None:
        LOGGER.info("Disconnecting from MQTT broker")
        self._client.loop_stop()
        self._client.disconnect()

    def subscribe(
        self,
        topic: str,
        callback: Callable[[mqtt.Client, Any, mqtt.MQTTMessage], None],
        qos: int = 1,
    ) -> None:
        LOGGER.debug("Subscribing to topic", extra={"topic": topic, "qos": qos})
        self._client.subscribe(topic, qos=qos)
        self._client.message_callback_add(topic, callback)

    def publish(
        self,
        topic: str,
        payload: Dict[str, Any] | str | bytes,
        options: Optional[PublishOptions] = None,
    ) -> None:
        opts = options or PublishOptions()
        data: bytes
        if isinstance(payload, bytes):
            data = payload
        elif isinstance(payload, str):
            data = payload.encode("utf-8")
        else:
            data = json.dumps(payload, separators=(",", ":")).encode("utf-8")

        LOGGER.debug(
            "Publishing MQTT message",
            extra={
                "topic": topic,
                "qos": opts.qos,
                "retain": opts.retain,
                "payload_len": len(data),
            },
        )
        self._client.publish(topic, data, qos=opts.qos, retain=opts.retain)


__all__ = ["MQTTClient", "PublishOptions"]
