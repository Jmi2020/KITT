"""Computer vision monitoring for print anomalies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import cv2
import numpy as np


@dataclass
class CVEvent:
    event_type: str
    confidence: float
    snapshot: bytes


class PrintMonitor:
    """Simple heuristic-based monitor for spaghetti detection."""

    def __init__(self, detection_callback: Callable[[CVEvent], None]) -> None:
        self._callback = detection_callback

    def process_frame(self, frame: bytes) -> None:
        image = cv2.imdecode(np.frombuffer(frame, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            return
        laplacian_var = cv2.Laplacian(image, cv2.CV_64F).var()
        if laplacian_var < 15:  # heuristically detect blur/spaghetti
            event = CVEvent(event_type="spaghetti_detected", confidence=0.6, snapshot=frame)
            self._callback(event)
