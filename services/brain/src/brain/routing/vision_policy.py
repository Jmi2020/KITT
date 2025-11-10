"""Simple heuristics to detect when the agent should fetch vision references."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import List

VISION_PATTERNS = [
    re.compile(r"\b(show|find|get)\s+(me\s+)?(pictures?|images?|photos?)\b", re.I),
    re.compile(r"\breference\s+images?\b", re.I),
    re.compile(r"\bgallery\b", re.I),
]

VISUAL_INDICATORS = {
    "image",
    "images",
    "photo",
    "photos",
    "picture",
    "pictures",
    "reference photo",
    "reference image",
    "visual reference",
    "moodboard",
    "inspiration image",
    "gallery",
}

EXTRACT_PATTERN = re.compile(r"images?\s+of\s+([a-z0-9\-\s]{3,40})", re.I)

VISUAL_KEYWORDS = {
    "duck",
    "gandalf",
    "wizard",
    "chair",
    "lamp",
    "bracket",
    "mount",
    "phone",
    "case",
    "gear",
    "hinge",
    "bottle",
    "mask",
    "helmet",
    "bike",
    "scooter",
    "dog",
    "cat",
    "handle",
    "foot",
    "boot",
}


@dataclass
class VisionPlan:
    should_suggest: bool
    targets: List[str]


def analyze_prompt(prompt: str) -> VisionPlan:
    text = prompt or ""
    lowered = text.lower()
    targets: List[str] = []

    for keyword in VISUAL_KEYWORDS:
        if keyword in lowered:
            targets.append(keyword)

    extract_match = EXTRACT_PATTERN.search(lowered)
    if extract_match:
        target = extract_match.group(1).strip()
        if target:
            targets.append(target)

    keyword_hit = any(token in lowered for token in VISUAL_INDICATORS)
    should = keyword_hit or any(pattern.search(text) for pattern in VISION_PATTERNS) or bool(targets)
    targets = _dedupe_preserve_order([t for t in targets if t])[:3]
    if should and not targets:
        fallback = text.strip()
        if len(fallback) > 60:
            fallback = fallback[:60]
        if fallback:
            targets.append(fallback)
    return VisionPlan(should_suggest=should, targets=targets)


def _dedupe_preserve_order(items: List[str]) -> List[str]:
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
