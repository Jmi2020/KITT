"""REST API routes for settings."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from .models import (
    AppSettings,
    CustomVoiceMode,
    FabricationSettings,
    NotificationSettings,
    PrivacySettings,
    SettingsResponse,
    SettingsUpdateRequest,
    UISettings,
    VoiceSettings,
)
from .storage import get_storage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings", tags=["settings"])

# Active WebSocket connections for sync
_sync_connections: dict[str, list[WebSocket]] = {}


@router.get("", response_model=SettingsResponse)
async def get_settings(user_id: str = "default") -> SettingsResponse:
    """Get all settings for a user."""
    storage = get_storage()
    record = storage.get_or_create_default(user_id)
    return SettingsResponse(
        settings=record.settings,
        user_id=record.user_id,
        updated_at=record.updated_at,
        version=record.version,
    )


@router.put("", response_model=SettingsResponse)
async def update_settings(
    request: SettingsUpdateRequest,
    user_id: str = "default",
) -> SettingsResponse:
    """Update settings for a user."""
    storage = get_storage()

    # Get existing settings
    existing = storage.get_or_create_default(user_id)
    current_settings = existing.settings.model_dump()

    # Apply updates
    if request.section:
        # Update specific section
        if request.section not in current_settings:
            raise HTTPException(status_code=400, detail=f"Unknown section: {request.section}")
        current_settings[request.section].update(request.settings)
    else:
        # Merge all settings
        for key, value in request.settings.items():
            if key in current_settings and isinstance(value, dict):
                current_settings[key].update(value)
            else:
                current_settings[key] = value

    # Save updated settings
    new_settings = AppSettings(**current_settings)
    record = storage.save_settings(user_id, new_settings, existing.version)

    # Broadcast to sync clients
    await _broadcast_update(user_id, record)

    return SettingsResponse(
        settings=record.settings,
        user_id=record.user_id,
        updated_at=record.updated_at,
        version=record.version,
    )


@router.get("/voice", response_model=VoiceSettings)
async def get_voice_settings(user_id: str = "default") -> VoiceSettings:
    """Get voice settings."""
    storage = get_storage()
    record = storage.get_or_create_default(user_id)
    return record.settings.voice


@router.put("/voice", response_model=VoiceSettings)
async def update_voice_settings(
    settings: VoiceSettings,
    user_id: str = "default",
) -> VoiceSettings:
    """Update voice settings."""
    storage = get_storage()
    existing = storage.get_or_create_default(user_id)
    existing.settings.voice = settings
    record = storage.save_settings(user_id, existing.settings, existing.version)
    await _broadcast_update(user_id, record)
    return record.settings.voice


@router.get("/fabrication", response_model=FabricationSettings)
async def get_fabrication_settings(user_id: str = "default") -> FabricationSettings:
    """Get fabrication settings."""
    storage = get_storage()
    record = storage.get_or_create_default(user_id)
    return record.settings.fabrication


@router.put("/fabrication", response_model=FabricationSettings)
async def update_fabrication_settings(
    settings: FabricationSettings,
    user_id: str = "default",
) -> FabricationSettings:
    """Update fabrication settings."""
    storage = get_storage()
    existing = storage.get_or_create_default(user_id)
    existing.settings.fabrication = settings
    record = storage.save_settings(user_id, existing.settings, existing.version)
    await _broadcast_update(user_id, record)
    return record.settings.fabrication


@router.get("/ui", response_model=UISettings)
async def get_ui_settings(user_id: str = "default") -> UISettings:
    """Get UI settings."""
    storage = get_storage()
    record = storage.get_or_create_default(user_id)
    return record.settings.ui


@router.put("/ui", response_model=UISettings)
async def update_ui_settings(
    settings: UISettings,
    user_id: str = "default",
) -> UISettings:
    """Update UI settings."""
    storage = get_storage()
    existing = storage.get_or_create_default(user_id)
    existing.settings.ui = settings
    record = storage.save_settings(user_id, existing.settings, existing.version)
    await _broadcast_update(user_id, record)
    return record.settings.ui


@router.get("/privacy", response_model=PrivacySettings)
async def get_privacy_settings(user_id: str = "default") -> PrivacySettings:
    """Get privacy settings."""
    storage = get_storage()
    record = storage.get_or_create_default(user_id)
    return record.settings.privacy


@router.put("/privacy", response_model=PrivacySettings)
async def update_privacy_settings(
    settings: PrivacySettings,
    user_id: str = "default",
) -> PrivacySettings:
    """Update privacy settings."""
    storage = get_storage()
    existing = storage.get_or_create_default(user_id)
    existing.settings.privacy = settings
    record = storage.save_settings(user_id, existing.settings, existing.version)
    await _broadcast_update(user_id, record)
    return record.settings.privacy


@router.get("/notifications", response_model=NotificationSettings)
async def get_notification_settings(user_id: str = "default") -> NotificationSettings:
    """Get notification settings."""
    storage = get_storage()
    record = storage.get_or_create_default(user_id)
    return record.settings.notifications


@router.put("/notifications", response_model=NotificationSettings)
async def update_notification_settings(
    settings: NotificationSettings,
    user_id: str = "default",
) -> NotificationSettings:
    """Update notification settings."""
    storage = get_storage()
    existing = storage.get_or_create_default(user_id)
    existing.settings.notifications = settings
    record = storage.save_settings(user_id, existing.settings, existing.version)
    await _broadcast_update(user_id, record)
    return record.settings.notifications


@router.get("/voice-modes", response_model=list[CustomVoiceMode])
async def get_voice_modes(user_id: str = "default") -> list[CustomVoiceMode]:
    """Get custom voice modes."""
    storage = get_storage()
    record = storage.get_or_create_default(user_id)
    return record.settings.custom_voice_modes


@router.put("/voice-modes", response_model=list[CustomVoiceMode])
async def update_voice_modes(
    modes: list[CustomVoiceMode],
    user_id: str = "default",
) -> list[CustomVoiceMode]:
    """Update custom voice modes."""
    storage = get_storage()
    existing = storage.get_or_create_default(user_id)
    existing.settings.custom_voice_modes = modes
    record = storage.save_settings(user_id, existing.settings, existing.version)
    await _broadcast_update(user_id, record)
    return record.settings.custom_voice_modes


@router.websocket("/sync")
async def settings_sync(websocket: WebSocket, user_id: str = "default"):
    """WebSocket for real-time settings sync across devices."""
    await websocket.accept()

    # Register connection
    if user_id not in _sync_connections:
        _sync_connections[user_id] = []
    _sync_connections[user_id].append(websocket)

    try:
        # Send current settings
        storage = get_storage()
        record = storage.get_or_create_default(user_id)
        await websocket.send_json({
            "type": "settings",
            "settings": record.settings.model_dump(),
            "version": record.version,
        })

        # Keep connection alive, handle incoming updates
        while True:
            data = await websocket.receive_json()

            if data.get("type") == "update":
                # Apply update from client
                updates = data.get("settings", {})
                section = data.get("section")

                existing = storage.get_or_create_default(user_id)
                current = existing.settings.model_dump()

                if section and section in current:
                    current[section].update(updates)
                else:
                    for key, value in updates.items():
                        if key in current and isinstance(value, dict):
                            current[key].update(value)

                new_settings = AppSettings(**current)
                record = storage.save_settings(user_id, new_settings, existing.version)

                # Broadcast to other connections
                await _broadcast_update(user_id, record, exclude=websocket)

                # Confirm to sender
                await websocket.send_json({
                    "type": "ack",
                    "version": record.version,
                })

            elif data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        pass
    finally:
        # Unregister connection
        if user_id in _sync_connections:
            _sync_connections[user_id] = [
                ws for ws in _sync_connections[user_id] if ws != websocket
            ]


async def _broadcast_update(user_id: str, record: Any, exclude: WebSocket | None = None):
    """Broadcast settings update to all sync connections."""
    if user_id not in _sync_connections:
        return

    message = {
        "type": "settings",
        "settings": record.settings.model_dump(),
        "version": record.version,
    }

    disconnected = []
    for ws in _sync_connections[user_id]:
        if ws == exclude:
            continue
        try:
            await ws.send_json(message)
        except Exception:
            disconnected.append(ws)

    # Clean up disconnected
    for ws in disconnected:
        _sync_connections[user_id].remove(ws)
