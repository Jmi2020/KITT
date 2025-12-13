# voice/kokoro_tts.py
"""
Kokoro TTS implementation with adaptive chunking for smooth playback.
Prevents stuttering on long texts by breaking into intelligently-sized chunks.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import threading
import queue
import time
from dataclasses import dataclass
from typing import AsyncIterator, Callable, Optional

import numpy as np

logger = logging.getLogger(__name__)

# Adaptive timing thresholds based on text length
ADAPTIVE_THRESHOLDS = [
    {"length": 100, "max_chars": 150, "initial_delay": 0.05, "chunk_delay": 0.02},
    {"length": 300, "max_chars": 180, "initial_delay": 0.08, "chunk_delay": 0.05},
    {"length": 800, "max_chars": 200, "initial_delay": 0.12, "chunk_delay": 0.08},
    {"length": float("inf"), "max_chars": 220, "initial_delay": 0.15, "chunk_delay": 0.10},
]


@dataclass
class TTSChunk:
    """A chunk of synthesized audio."""
    samples: np.ndarray
    sample_rate: int
    chunk_index: int
    total_chunks: int
    text: str


class KokoroTTS:
    """
    Kokoro TTS with adaptive chunking for streaming playback.

    Features:
    - Intelligent text chunking by sentence/punctuation
    - Adaptive timing based on text length
    - Background generation for smooth streaming
    - Markdown/formatting cleanup for natural speech
    """

    def __init__(
        self,
        voice: Optional[str] = None,
        speed: float = 1.0,
        lang: str = "en-us",
    ):
        """
        Initialize Kokoro TTS.

        Args:
            voice: Voice model (default from KOKORO_DEFAULT_VOICE env)
            speed: Speech speed multiplier (1.0 = normal)
            lang: Language code
        """
        self.voice = voice or os.getenv("KOKORO_DEFAULT_VOICE", "am_michael")
        self.speed = speed
        self.lang = lang
        self._manager = None
        self._chunk_queue: queue.Queue = queue.Queue()
        self._generation_complete = threading.Event()

    @property
    def manager(self):
        """Lazy-load the Kokoro manager."""
        if self._manager is None:
            from .kokoro_manager import KokoroManager
            self._manager = KokoroManager.get_instance()
        return self._manager

    def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        """
        Synthesize text to audio (blocking, full text).

        Args:
            text: Text to synthesize

        Returns:
            Tuple of (samples, sample_rate)
        """
        cleaned = self._clean_text(text)
        return self.manager.create(cleaned, voice=self.voice, speed=self.speed, lang=self.lang)

    async def synthesize_streaming(
        self,
        text: str,
        on_chunk: Optional[Callable[[TTSChunk], None]] = None,
    ) -> AsyncIterator[TTSChunk]:
        """
        Synthesize text with streaming chunks for smooth playback.

        Yields chunks as they're generated, with background processing
        for subsequent chunks to prevent gaps.

        Args:
            text: Text to synthesize
            on_chunk: Optional callback for each chunk

        Yields:
            TTSChunk objects containing audio samples
        """
        self._generation_complete.clear()
        while not self._chunk_queue.empty():
            try:
                self._chunk_queue.get_nowait()
            except queue.Empty:
                break

        cleaned = self._clean_text(text)
        chunks = self._split_into_chunks(cleaned)

        if not chunks:
            return

        total = len(chunks)
        logger.info(f"Synthesizing {total} chunks from {len(cleaned)} chars")

        # Get adaptive timing parameters
        params = self._get_timing_params(len(cleaned))
        logger.debug(f"Using timing: max_chars={params['max_chars']}, delay={params['initial_delay']:.3f}s")

        # Generate first chunk synchronously
        first_chunk = await self._generate_chunk(chunks[0], 0, total)
        if on_chunk:
            on_chunk(first_chunk)
        yield first_chunk

        # Start background generation for remaining chunks
        if total > 1:
            bg_thread = threading.Thread(
                target=self._generate_remaining,
                args=(chunks[1:], total, params["chunk_delay"]),
                daemon=True,
            )
            bg_thread.start()

            # Small head start for background generation
            await asyncio.sleep(params["initial_delay"])

            # Yield chunks as they become available
            yielded = 1
            while yielded < total:
                try:
                    chunk = self._chunk_queue.get(timeout=3.0)
                    if on_chunk:
                        on_chunk(chunk)
                    yield chunk
                    yielded += 1
                except queue.Empty:
                    if self._generation_complete.is_set():
                        break
                    logger.warning("Chunk timeout - generation may be slow")

        self._generation_complete.set()

    async def _generate_chunk(self, text: str, index: int, total: int) -> TTSChunk:
        """Generate a single chunk."""
        loop = asyncio.get_event_loop()
        samples, rate = await loop.run_in_executor(
            None,
            lambda: self.manager.create(text, voice=self.voice, speed=self.speed, lang=self.lang),
        )
        return TTSChunk(
            samples=samples,
            sample_rate=rate,
            chunk_index=index,
            total_chunks=total,
            text=text,
        )

    def _generate_remaining(self, chunks: list[str], total: int, delay: float) -> None:
        """Background thread for generating remaining chunks."""
        try:
            for i, text in enumerate(chunks, start=1):
                if not text.strip():
                    continue

                if i > 1 and delay > 0:
                    time.sleep(delay)

                start = time.time()
                samples, rate = self.manager.create(
                    text, voice=self.voice, speed=self.speed, lang=self.lang
                )
                elapsed = time.time() - start

                chunk = TTSChunk(
                    samples=samples,
                    sample_rate=rate,
                    chunk_index=i,
                    total_chunks=total,
                    text=text,
                )
                self._chunk_queue.put(chunk)
                logger.debug(f"Generated chunk {i+1}/{total} in {elapsed:.3f}s")

        except Exception as e:
            logger.error(f"Background generation error: {e}")
        finally:
            self._generation_complete.set()

    def _clean_text(self, text: str) -> str:
        """Remove markdown and formatting for natural speech."""
        # Remove markdown emphasis
        cleaned = re.sub(r"\*+([^*]+)\*+", r"\1", text)
        cleaned = cleaned.replace("*", "")
        cleaned = cleaned.replace("_", "")
        cleaned = cleaned.replace("`", "")
        # Normalize whitespace
        cleaned = " ".join(cleaned.split())
        return cleaned

    def _split_into_chunks(self, text: str) -> list[str]:
        """Split text into chunks optimized for TTS."""
        params = self._get_timing_params(len(text))
        max_chars = params["max_chars"]

        # Try sentence-based splitting first
        sentences = self._split_sentences(text)
        chunks = []
        current = ""

        for sentence in sentences:
            if len(current) + len(sentence) > max_chars and current:
                chunks.append(current.strip())
                current = sentence
            else:
                current = f"{current} {sentence}".strip() if current else sentence

        if current:
            chunks.append(current.strip())

        # Further split any oversized chunks
        final = []
        for chunk in chunks:
            if len(chunk) > max_chars:
                final.extend(self._split_by_punctuation(chunk, max_chars))
            else:
                final.append(chunk)

        return [c for c in final if c.strip()]

    def _split_sentences(self, text: str) -> list[str]:
        """Split text into sentences."""
        # Simple sentence splitting (could use nltk for better results)
        pattern = r"(?<=[.!?])\s+"
        return re.split(pattern, text)

    def _split_by_punctuation(self, text: str, max_chars: int) -> list[str]:
        """Split oversized text by punctuation marks."""
        parts = re.split(r"[,;:]", text)
        chunks = []
        current = ""

        for part in parts:
            part = part.strip()
            if not part:
                continue
            if len(current) + len(part) > max_chars and current:
                chunks.append(current.strip())
                current = part
            else:
                current = f"{current}, {part}".strip(", ") if current else part

        if current:
            chunks.append(current)

        return chunks

    def _get_timing_params(self, text_length: int) -> dict:
        """Get adaptive timing parameters based on text length."""
        for threshold in ADAPTIVE_THRESHOLDS:
            if text_length < threshold["length"]:
                return threshold
        return ADAPTIVE_THRESHOLDS[-1]


# Convenience function for simple synthesis
async def synthesize_text(
    text: str,
    voice: Optional[str] = None,
    speed: float = 1.0,
) -> tuple[np.ndarray, int]:
    """
    Simple text-to-speech synthesis.

    Args:
        text: Text to synthesize
        voice: Voice model (optional)
        speed: Speech speed

    Returns:
        Tuple of (samples, sample_rate)
    """
    tts = KokoroTTS(voice=voice, speed=speed)
    return tts.synthesize(text)
