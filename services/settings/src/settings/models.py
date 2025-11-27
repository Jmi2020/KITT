"""Settings data models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class VoiceSettings(BaseModel):
    """Voice assistant settings."""

    voice: str = Field(default="alloy", description="TTS voice")
    language: str = Field(default="en", description="STT language")
    hotword: str = Field(default="kitty", description="Wake word")
    prefer_local: bool = Field(default=True, description="Prefer local STT/TTS")
    sample_rate: int = Field(default=16000, description="Audio sample rate")
    push_to_talk: bool = Field(default=True, description="Require push-to-talk")


class FabricationSettings(BaseModel):
    """Fabrication/printing settings."""

    default_material: str = Field(default="pla_black_esun", description="Default material ID")
    default_profile: str = Field(default="standard", description="Default print profile")
    safety_confirmation: bool = Field(default=True, description="Require confirmation for hazardous ops")
    auto_slice: bool = Field(default=False, description="Auto-slice new models")
    default_printer: Optional[str] = Field(default=None, description="Preferred printer")


class UISettings(BaseModel):
    """UI appearance settings."""

    theme: str = Field(default="dark", description="UI theme (dark/light)")
    compact_mode: bool = Field(default=False, description="Compact UI mode")
    show_debug: bool = Field(default=False, description="Show debug info")
    default_view: str = Field(default="shell", description="Default view on load")
    sidebar_collapsed: bool = Field(default=False, description="Sidebar collapsed state")


class PrivacySettings(BaseModel):
    """Privacy and data settings."""

    store_conversations: bool = Field(default=True, description="Store conversation history")
    telemetry_enabled: bool = Field(default=False, description="Send anonymous telemetry")
    local_only: bool = Field(default=False, description="Prefer local-only processing")


class NotificationSettings(BaseModel):
    """Notification preferences."""

    print_complete: bool = Field(default=True, description="Notify on print completion")
    print_failure: bool = Field(default=True, description="Notify on print failure")
    low_inventory: bool = Field(default=True, description="Notify on low material")
    sound_enabled: bool = Field(default=True, description="Enable notification sounds")


class AppSettings(BaseModel):
    """Complete application settings."""

    voice: VoiceSettings = Field(default_factory=VoiceSettings)
    fabrication: FabricationSettings = Field(default_factory=FabricationSettings)
    ui: UISettings = Field(default_factory=UISettings)
    privacy: PrivacySettings = Field(default_factory=PrivacySettings)
    notifications: NotificationSettings = Field(default_factory=NotificationSettings)


class UserSettingsRecord(BaseModel):
    """Database record for user settings."""

    user_id: str
    settings: AppSettings
    created_at: datetime
    updated_at: datetime
    version: int = 1


class SettingsUpdateRequest(BaseModel):
    """Request to update settings."""

    settings: dict[str, Any]
    section: Optional[str] = None  # If specified, only update this section


class SettingsResponse(BaseModel):
    """Settings response with metadata."""

    settings: AppSettings
    user_id: str
    updated_at: datetime
    version: int
