"""Manage fabrication job lifecycle actions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from common.logging import get_logger

from ..octoprint.client import OctoPrintClient

LOGGER = get_logger(__name__)


@dataclass
class PrintJobRequest:
    job_id: str
    gcode_path: Path
    nozzle_temp: int
    bed_temp: int


class PrintJobManager:
    def __init__(self, client: OctoPrintClient) -> None:
        self._client = client

    async def start_job(self, request: PrintJobRequest) -> None:
        LOGGER.info("Uploading gcode", job=request.job_id)
        await self._client.upload_file(request.gcode_path)
        await self._client.set_tool_temperature(request.nozzle_temp)
        await self._client.set_bed_temperature(request.bed_temp)
        await self._client.start_job()

    async def pause_job(self, reason: Optional[str] = None) -> None:
        LOGGER.warning("Pausing job", reason=reason)
        await self._client.pause_job()
