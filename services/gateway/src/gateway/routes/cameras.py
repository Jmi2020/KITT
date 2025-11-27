"""WebSocket endpoint for camera streaming.

Provides real-time camera feed broadcasting using native WebSocket.
Cameras publish frames, viewers subscribe to receive them.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/cameras", tags=["cameras"])


@dataclass
class CameraInfo:
    """Information about a connected camera."""

    camera_id: str
    friendly_name: str
    websocket: WebSocket
    last_seen: float = field(default_factory=time.time)
    resolution: tuple[int, int] = (640, 480)
    fps: int = 15


@dataclass
class ViewerInfo:
    """Information about a viewer connection."""

    viewer_id: str
    websocket: WebSocket
    subscribed_cameras: set[str] = field(default_factory=set)


# Global state for connected cameras and viewers
_cameras: dict[str, CameraInfo] = {}
_viewers: dict[str, ViewerInfo] = {}
_last_frames: dict[str, dict[str, Any]] = {}  # Cache last frame per camera


@router.get("")
async def list_cameras() -> list[dict]:
    """List all connected cameras."""
    return [
        {
            "camera_id": cam.camera_id,
            "friendly_name": cam.friendly_name,
            "last_seen": cam.last_seen,
            "resolution": cam.resolution,
            "fps": cam.fps,
            "online": time.time() - cam.last_seen < 30,
        }
        for cam in _cameras.values()
    ]


@router.get("/{camera_id}/frame")
async def get_last_frame(camera_id: str) -> dict:
    """Get the last captured frame from a camera."""
    if camera_id not in _last_frames:
        return {"error": "No frame available", "camera_id": camera_id}
    return _last_frames[camera_id]


@router.websocket("/stream")
async def camera_stream(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for camera streaming.

    Protocol:
    - Cameras send: {"type": "register", "camera_id": "...", "name": "..."}
    - Cameras send: {"type": "frame", "jpeg_base64": "..."}
    - Viewers send: {"type": "subscribe", "camera_id": "..."}
    - Viewers send: {"type": "unsubscribe", "camera_id": "..."}
    - Server broadcasts frames to subscribed viewers
    """
    await websocket.accept()

    connection_id = str(uuid.uuid4())
    connection_type: str | None = None
    camera_id: str | None = None

    try:
        # Send initial status
        await websocket.send_json({
            "type": "status",
            "status": "connected",
            "connection_id": connection_id,
            "cameras": [
                {
                    "camera_id": cam.camera_id,
                    "friendly_name": cam.friendly_name,
                    "online": time.time() - cam.last_seen < 30,
                }
                for cam in _cameras.values()
            ],
        })

        while True:
            try:
                message = await websocket.receive()

                if message["type"] == "websocket.disconnect":
                    break

                if "text" in message:
                    data = json.loads(message["text"])
                    msg_type = data.get("type")

                    if msg_type == "register":
                        # Camera registration
                        camera_id = data.get("camera_id", connection_id)
                        friendly_name = data.get("name", f"Camera {camera_id[:8]}")

                        _cameras[camera_id] = CameraInfo(
                            camera_id=camera_id,
                            friendly_name=friendly_name,
                            websocket=websocket,
                            resolution=tuple(data.get("resolution", [640, 480])),
                            fps=data.get("fps", 15),
                        )
                        connection_type = "camera"

                        # Notify all viewers about new camera
                        await _broadcast_to_viewers({
                            "type": "camera_joined",
                            "camera_id": camera_id,
                            "friendly_name": friendly_name,
                        })

                        await websocket.send_json({
                            "type": "registered",
                            "camera_id": camera_id,
                        })

                        logger.info("Camera registered: %s (%s)", camera_id, friendly_name)

                    elif msg_type == "frame" and camera_id and camera_id in _cameras:
                        # Frame from camera
                        _cameras[camera_id].last_seen = time.time()

                        frame_data = {
                            "type": "frame",
                            "camera_id": camera_id,
                            "jpeg_base64": data.get("jpeg_base64", ""),
                            "timestamp": time.time(),
                        }

                        # Cache last frame
                        _last_frames[camera_id] = frame_data

                        # Broadcast to subscribed viewers
                        await _broadcast_frame(camera_id, frame_data)

                    elif msg_type == "subscribe":
                        # Viewer subscribing to camera
                        target_camera = data.get("camera_id")
                        if connection_id not in _viewers:
                            _viewers[connection_id] = ViewerInfo(
                                viewer_id=connection_id,
                                websocket=websocket,
                            )
                            connection_type = "viewer"

                        if target_camera:
                            _viewers[connection_id].subscribed_cameras.add(target_camera)

                            # Send last frame if available
                            if target_camera in _last_frames:
                                await websocket.send_json(_last_frames[target_camera])

                            await websocket.send_json({
                                "type": "subscribed",
                                "camera_id": target_camera,
                            })

                    elif msg_type == "unsubscribe":
                        # Viewer unsubscribing from camera
                        target_camera = data.get("camera_id")
                        if connection_id in _viewers and target_camera:
                            _viewers[connection_id].subscribed_cameras.discard(target_camera)
                            await websocket.send_json({
                                "type": "unsubscribed",
                                "camera_id": target_camera,
                            })

                    elif msg_type == "request_cameras":
                        # Viewer requesting camera list
                        await websocket.send_json({
                            "type": "cameras_list",
                            "cameras": [
                                {
                                    "camera_id": cam.camera_id,
                                    "friendly_name": cam.friendly_name,
                                    "online": time.time() - cam.last_seen < 30,
                                }
                                for cam in _cameras.values()
                            ],
                        })

                elif "bytes" in message:
                    # Binary frame data (more efficient than base64)
                    if camera_id and camera_id in _cameras:
                        _cameras[camera_id].last_seen = time.time()

                        # Convert to base64 for JSON transmission to viewers
                        jpeg_base64 = base64.b64encode(message["bytes"]).decode("ascii")

                        frame_data = {
                            "type": "frame",
                            "camera_id": camera_id,
                            "jpeg_base64": jpeg_base64,
                            "timestamp": time.time(),
                        }

                        _last_frames[camera_id] = frame_data
                        await _broadcast_frame(camera_id, frame_data)

            except WebSocketDisconnect:
                break

    except Exception as e:
        logger.exception("Camera WebSocket error: %s", e)

    finally:
        # Cleanup
        if connection_type == "camera" and camera_id:
            _cameras.pop(camera_id, None)
            _last_frames.pop(camera_id, None)
            await _broadcast_to_viewers({
                "type": "camera_left",
                "camera_id": camera_id,
            })
            logger.info("Camera disconnected: %s", camera_id)

        elif connection_type == "viewer":
            _viewers.pop(connection_id, None)


async def _broadcast_frame(camera_id: str, frame_data: dict) -> None:
    """Broadcast frame to all viewers subscribed to this camera."""
    disconnected = []

    for viewer_id, viewer in _viewers.items():
        if camera_id in viewer.subscribed_cameras:
            try:
                await viewer.websocket.send_json(frame_data)
            except Exception:
                disconnected.append(viewer_id)

    # Remove disconnected viewers
    for viewer_id in disconnected:
        _viewers.pop(viewer_id, None)


async def _broadcast_to_viewers(message: dict) -> None:
    """Broadcast a message to all viewers."""
    disconnected = []

    for viewer_id, viewer in _viewers.items():
        try:
            await viewer.websocket.send_json(message)
        except Exception:
            disconnected.append(viewer_id)

    for viewer_id in disconnected:
        _viewers.pop(viewer_id, None)
