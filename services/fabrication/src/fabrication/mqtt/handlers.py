"""MQTT handlers for fabrication commands."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict

from common.messaging import MQTTClient, PublishOptions

from ..jobs.manager import PrintJobManager, PrintJobRequest


class FabricationMQTTHandler:
    def __init__(self, mqtt_client: MQTTClient, manager: PrintJobManager) -> None:
        self._mqtt = mqtt_client
        self._manager = manager

    def start(self) -> None:
        self._mqtt.connect()
        self._mqtt.subscribe("jarvis/devices/+/cmd", self._on_message)

    def _on_message(self, client, userdata, message):  # type: ignore[override]
        payload = json.loads(message.payload.decode("utf-8"))
        intent = payload.get("intent")
        if intent == "start_print":
            asyncio.create_task(self._handle_start(payload))
        elif intent == "pause_print":
            asyncio.create_task(self._manager.pause_job(reason="requested"))

    async def _handle_start(self, payload: Dict[str, Any]) -> None:
        job = PrintJobRequest(
            job_id=payload["jobId"],
            gcode_path=Path(payload["gcodePath"]),
            nozzle_temp=payload.get("nozzleTemp", 215),
            bed_temp=payload.get("bedTemp", 60),
        )
        await self._manager.start_job(job)
        self._mqtt.publish(
            f"jarvis/devices/{payload['deviceId']}/state",
            {"status": "printing", "jobId": job.job_id},
            options=PublishOptions(qos=1, retain=True),
        )
