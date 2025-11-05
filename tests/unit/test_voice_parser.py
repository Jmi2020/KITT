import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "services/voice/src"))
sys.path.append(str(ROOT / "services/common/src"))

pytest.importorskip("pydantic")
pytest.importorskip("pydantic_settings")

from voice.parser import VoiceParser  # type: ignore[import]


def test_parser_defaults_to_routing():
    parser = VoiceParser()
    command = parser.parse("start a new project for a phone stand")
    assert command["type"] == "routing"
    assert "project" in command["prompt"].lower()


def test_parser_detects_note():
    parser = VoiceParser()
    command = parser.parse("note that the prototype needs 5 percent infill")
    assert command["type"] == "note"
    assert "prototype" in command["summary"].lower()


def test_parser_detects_device_command():
    parser = VoiceParser()
    command = parser.parse("turn on the welding lights")
    assert command["type"] == "device"
    assert command["intent"] == "light.turn_on"
    assert command["payload"]["deviceId"] == "welding-lights"
