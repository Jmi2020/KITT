# ruff: noqa: E402
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "services/brain/src"))

from brain.routing.vision_policy import analyze_prompt  # type: ignore[import]


@pytest.mark.parametrize(
    "prompt,expected",
    [
        ("show me pictures of ducks", True),
        ("design a duck bracket", True),
        ("hello world", False),
    ],
)
def test_analyze_prompt(prompt, expected):
    plan = analyze_prompt(prompt)
    assert plan.should_suggest is expected
    if expected:
        assert plan.targets
    else:
        assert plan.targets == []
