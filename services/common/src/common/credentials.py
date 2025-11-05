"""Typed credential containers for integrations."""

from __future__ import annotations

from pydantic import BaseModel, SecretStr


class HomeAssistantCredentials(BaseModel):
    token: SecretStr
    base_url: str


class OctoPrintCredentials(BaseModel):
    api_key: SecretStr
    base_url: str


class ZooCredentials(BaseModel):
    api_key: SecretStr


class TripoCredentials(BaseModel):
    api_key: SecretStr


class UniFiCredentials(BaseModel):
    host: str
    username: str
    password: SecretStr


class TailscaleCredentials(BaseModel):
    api_key: SecretStr


__all__ = [
    "HomeAssistantCredentials",
    "OctoPrintCredentials",
    "ZooCredentials",
    "TripoCredentials",
    "UniFiCredentials",
    "TailscaleCredentials",
]
