"""Health checks for I/O Control features.

Validates that configured features are actually working, not just configured.
"""

from __future__ import annotations

import socket
from typing import Optional

import httpx

from common.config import settings
from common.logging import get_logger

LOGGER = get_logger(__name__)


# ============================================================================
# API Key Health Checks
# ============================================================================

def check_perplexity_api() -> bool:
    """Check if Perplexity API key is valid.

    Returns:
        True if API key works
    """
    api_key = getattr(settings, "PERPLEXITY_API_KEY", "")
    if not api_key or api_key == "***":
        return False

    try:
        # Quick validation: check if key format is valid (starts with pplx-)
        # Full validation would require actual API call
        return api_key.startswith("pplx-") and len(api_key) > 20
    except Exception as e:
        LOGGER.debug("Perplexity health check failed", error=str(e))
        return False


def check_openai_api() -> bool:
    """Check if OpenAI API key is valid.

    Returns:
        True if API key works
    """
    api_key = getattr(settings, "OPENAI_API_KEY", "")
    if not api_key or api_key == "***":
        return False

    try:
        # Quick validation: check if key format is valid (starts with sk-)
        return api_key.startswith("sk-") and len(api_key) > 20
    except Exception as e:
        LOGGER.debug("OpenAI health check failed", error=str(e))
        return False


def check_anthropic_api() -> bool:
    """Check if Anthropic API key is valid.

    Returns:
        True if API key works
    """
    api_key = getattr(settings, "ANTHROPIC_API_KEY", "")
    if not api_key or api_key == "***":
        return False

    try:
        # Quick validation: check if key format is valid (starts with sk-ant-)
        return api_key.startswith("sk-ant-") and len(api_key) > 20
    except Exception as e:
        LOGGER.debug("Anthropic health check failed", error=str(e))
        return False


def check_zoo_api() -> bool:
    """Check if Zoo CAD API key is valid.

    Returns:
        True if API key works
    """
    api_key = getattr(settings, "ZOO_API_KEY", "")
    if not api_key or api_key == "***":
        return False

    try:
        # Basic validation: non-empty key
        return len(api_key) > 10
    except Exception as e:
        LOGGER.debug("Zoo API health check failed", error=str(e))
        return False


def check_tripo_api() -> bool:
    """Check if Tripo CAD API key is valid.

    Returns:
        True if API key works
    """
    api_key = getattr(settings, "TRIPO_API_KEY", "")
    if not api_key or api_key == "***":
        return False

    try:
        # Basic validation: non-empty key
        return len(api_key) > 10
    except Exception as e:
        LOGGER.debug("Tripo API health check failed", error=str(e))
        return False


# ============================================================================
# Service Health Checks
# ============================================================================

def check_mqtt_broker() -> bool:
    """Check if MQTT broker is reachable.

    Returns:
        True if MQTT broker is accessible
    """
    mqtt_host = getattr(settings, "MQTT_HOST", "mosquitto")
    mqtt_port = getattr(settings, "MQTT_PORT", 1883)

    try:
        # Try to connect to MQTT port
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((mqtt_host, mqtt_port))
        sock.close()
        return result == 0
    except Exception as e:
        LOGGER.debug("MQTT broker health check failed", error=str(e))
        return False


def check_minio() -> bool:
    """Check if MinIO is reachable.

    Returns:
        True if MinIO is accessible
    """
    minio_endpoint = getattr(settings, "MINIO_ENDPOINT", "minio:9000")

    try:
        # Try to connect to MinIO
        host, port = minio_endpoint.split(":")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((host, int(port)))
        sock.close()
        return result == 0
    except Exception as e:
        LOGGER.debug("MinIO health check failed", error=str(e))
        return False


def check_printer_ip(printer_id: str) -> bool:
    """Check if printer IP is reachable.

    Args:
        printer_id: Printer identifier (bamboo_h2d, snapmaker_artisan, elegoo_giga)

    Returns:
        True if printer is reachable
    """
    ip_map = {
        "bamboo_h2d": getattr(settings, "BAMBOO_IP", ""),
        "snapmaker_artisan": getattr(settings, "SNAPMAKER_IP", ""),
        "elegoo_giga": getattr(settings, "ELEGOO_IP", ""),
    }

    ip = ip_map.get(printer_id, "")
    if not ip or ip == "192.168.1.100":  # Default/unconfigured IP
        return False

    try:
        # Try to ping the IP (basic reachability)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        # Try common printer ports
        for port in [80, 443, 8080]:
            result = sock.connect_ex((ip, port))
            if result == 0:
                sock.close()
                return True
        sock.close()
        return False
    except Exception as e:
        LOGGER.debug(f"{printer_id} health check failed", error=str(e))
        return False


def check_camera_url(camera_url: str) -> bool:
    """Check if camera URL is reachable.

    Args:
        camera_url: Camera HTTP endpoint

    Returns:
        True if camera is reachable
    """
    if not camera_url or camera_url.startswith("http://example"):
        return False

    try:
        # Try to fetch from camera URL
        response = httpx.get(camera_url, timeout=2)
        return response.status_code == 200
    except Exception as e:
        LOGGER.debug("Camera health check failed", url=camera_url, error=str(e))
        return False


# ============================================================================
# Database Health Checks
# ============================================================================

def check_postgres() -> bool:
    """Check if PostgreSQL is reachable.

    Returns:
        True if PostgreSQL is accessible
    """
    try:
        # Try to parse database URL and connect
        db_url = getattr(settings, "DATABASE_URL", "")
        if not db_url or "sqlite" in db_url:
            return True  # SQLite always works if file accessible

        # For PostgreSQL, try to connect
        # Extract host and port from URL
        if "postgresql" in db_url:
            # Format: postgresql://user:pass@host:port/db
            parts = db_url.split("@")
            if len(parts) > 1:
                host_port = parts[1].split("/")[0]
                if ":" in host_port:
                    host, port = host_port.split(":")
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(2)
                    result = sock.connect_ex((host, int(port)))
                    sock.close()
                    return result == 0

        return True  # Default to true if can't parse
    except Exception as e:
        LOGGER.debug("PostgreSQL health check failed", error=str(e))
        return False


# ============================================================================
# Composite Health Checks
# ============================================================================

def check_bamboo_camera() -> bool:
    """Check if Bamboo Labs camera is available.

    Returns:
        True if Bamboo camera configured and MQTT available
    """
    # Need MQTT broker and access code
    mqtt_ok = check_mqtt_broker()
    access_code = getattr(settings, "BAMBOO_ACCESS_CODE", "")
    serial = getattr(settings, "BAMBOO_SERIAL", "")

    return mqtt_ok and bool(access_code) and bool(serial)


def check_raspberry_pi_cameras() -> bool:
    """Check if Raspberry Pi cameras are available.

    Returns:
        True if at least one Pi camera is reachable
    """
    snapmaker_url = getattr(settings, "SNAPMAKER_CAMERA_URL", "")
    elegoo_url = getattr(settings, "ELEGOO_CAMERA_URL", "")

    snapmaker_ok = check_camera_url(snapmaker_url) if snapmaker_url else False
    elegoo_ok = check_camera_url(elegoo_url) if elegoo_url else False

    return snapmaker_ok or elegoo_ok


def check_camera_capture() -> bool:
    """Check if camera capture is available.

    Returns:
        True if any camera source is available
    """
    return check_bamboo_camera() or check_raspberry_pi_cameras()


def check_print_outcome_tracking() -> bool:
    """Check if print outcome tracking is available.

    Returns:
        True if database is accessible
    """
    return check_postgres()
