"""Hermes 3 summarizer for condensing verbose agent outputs."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from .config import LlamaCppConfig
from .llama_cpp_client import LlamaCppClient

logger = logging.getLogger(__name__)


def _env_bool(value: Optional[str], default: bool = True) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


class HermesSummarizer:
    """Wrapper around a dedicated llama.cpp server that produces summaries."""

    def __init__(
        self,
        client: Optional[LlamaCppClient] = None,
    ) -> None:
        self.alias = os.getenv("LLAMACPP_SUMMARY_ALIAS", "kitty-summary")
        self._enabled = _env_bool(
            os.getenv("HERMES_SUMMARY_ENABLED"),
            default=_env_bool(os.getenv("LLAMACPP_SUMMARY_ENABLED", "1")),
        )
        self.min_chars = int(os.getenv("HERMES_SUMMARY_MIN_CHARS", "1600"))
        self.max_answer_chars = int(os.getenv("HERMES_SUMMARY_MAX_INPUT_CHARS", "6000"))
        self.max_agent_chars = int(os.getenv("HERMES_SUMMARY_AGENT_CHAR_LIMIT", "2500"))

        if not self._enabled:
            logger.info("Hermes summarizer disabled via env")
            self._client = None
            return

        if client:
            self._client = client
            return

        host = os.getenv("LLAMACPP_SUMMARY_HOST", "http://localhost:8085")
        cfg = LlamaCppConfig(
            host=host,
            n_predict=int(os.getenv("LLAMACPP_SUMMARY_N_PREDICT", "640")),
            temperature=float(os.getenv("LLAMACPP_SUMMARY_TEMPERATURE", "0.2")),
            top_p=float(os.getenv("LLAMACPP_SUMMARY_TOP_P", "0.9")),
            repeat_penalty=float(os.getenv("LLAMACPP_SUMMARY_REPEAT_PENALTY", "1.05")),
            timeout_seconds=float(os.getenv("LLAMACPP_SUMMARY_TIMEOUT", "45")),
            stream=False,
            model_alias=self.alias,
        )
        self._client = LlamaCppClient(config=cfg)

    @property
    def enabled(self) -> bool:
        return bool(self._client)

    def should_summarize(self, *, output_len: int, truncated: bool, has_agent_steps: bool) -> bool:
        if not self.enabled:
            return False
        if truncated:
            return True
        if has_agent_steps and output_len >= max(800, self.min_chars // 2):
            return True
        return output_len >= self.min_chars

    async def summarize(
        self,
        final_answer: str,
        agent_steps: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[str]:
        if not self.enabled or not final_answer.strip():
            return None

        prompt = self._build_prompt(final_answer, agent_steps or [])
        try:
            response = await self._client.generate(prompt, model=self.alias)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Hermes summarizer call failed: %s", exc)
            self._client = None
            return None

        summary = (response or {}).get("response")
        return summary.strip() if summary else None

    def _build_prompt(self, answer: str, steps: List[Dict[str, Any]]) -> str:
        if len(answer) > self.max_answer_chars:
            limited_answer = answer[: self.max_answer_chars] + "\n... [truncated]"
        else:
            limited_answer = answer
        agent_notes = self._format_agent_steps(steps)
        if agent_notes:
            agent_section = f"<agent_trace>\n{agent_notes}\n</agent_trace>"
        else:
            agent_section = "<agent_trace>None</agent_trace>"

        return (
            "You are a Hermes 3 summarizer that rewrites verbose research outputs "
            "into concise but information-rich briefs."
            "\n\n"
            "Summarize the final answer and, if provided, incorporate any critical findings "
            "from the agent trace. Highlight:"
            "\n- Direct answers to the user request"
            "\n- Tool findings (sources, URLs, stats)"
            "\n- Outstanding TODOs or follow-ups"
            "\n\nKeep the result under 300 words, use tight prose or short bullet lists, and avoid filler."
            f"\n\n<final_answer>\n{limited_answer}\n</final_answer>\n{agent_section}"
        )

    def _format_agent_steps(self, steps: List[Dict[str, Any]]) -> str:
        if not steps:
            return ""
        parts: List[str] = []
        for idx, step in enumerate(steps, 1):
            lines = [f"Step {idx}:"]
            for key in ("thought", "action", "observation"):
                value = step.get(key)
                if value:
                    lines.append(f"{key}: {value}")
            parts.append(" | ".join(lines))
            joined = "\n".join(parts)
            if len(joined) > self.max_agent_chars:
                return joined[: self.max_agent_chars] + "\n... [agent trace truncated]"
        return "\n".join(parts)


__all__ = ["HermesSummarizer"]
