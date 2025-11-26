"""Hybrid Speech-to-Text with local Whisper and OpenAI fallback.

Prioritizes local Whisper.cpp for offline-first operation,
falls back to OpenAI Whisper API when local fails or is unavailable.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class STTProvider(ABC):
    """Abstract base class for STT providers."""

    @abstractmethod
    async def transcribe(
        self,
        audio: bytes,
        language: str = "en",
        sample_rate: int = 16000,
    ) -> str:
        """Transcribe audio bytes to text."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is available."""
        ...


class WhisperCppClient(STTProvider):
    """Local Whisper.cpp STT client.

    Uses whisper-cpp-python bindings for local transcription.
    Requires a downloaded Whisper model.
    """

    def __init__(
        self,
        model_path: str | None = None,
        model_size: str = "base.en",
    ) -> None:
        self._model_path = model_path
        self._model_size = model_size
        self._whisper = None
        self._available = False
        self._init_lock = asyncio.Lock()

        # Check if local Whisper *could* be available (before lazy loading)
        self._can_be_available = self._check_prerequisites()

    def _check_prerequisites(self) -> bool:
        """Check if Whisper prerequisites are met (library + model)."""
        try:
            # Check if whispercpp can be imported
            from whispercpp import Whisper  # noqa: F401

            # Check if model file exists
            if self._model_path and Path(self._model_path).exists():
                logger.info("Local Whisper available: model at %s", self._model_path)
                return True

            # Check default location
            model_dir = Path.home() / ".cache" / "whisper"
            model_file = model_dir / f"ggml-{self._model_size}.bin"
            if model_file.exists():
                logger.info("Local Whisper available: model at %s", model_file)
                return True

            logger.warning("Local Whisper: library OK but model not found")
            return False

        except ImportError:
            logger.warning("Local Whisper unavailable: whispercpp not installed")
            return False
        except Exception as e:
            logger.warning("Local Whisper check failed: %s", e)
            return False

    async def _ensure_initialized(self) -> None:
        """Lazy initialization of Whisper model."""
        if self._whisper is not None:
            return

        async with self._init_lock:
            if self._whisper is not None:
                return

            try:
                # Try to import whisper-cpp-python
                from whispercpp import Whisper

                # Find or download model
                model_path = self._model_path
                if not model_path:
                    # Check common locations
                    model_dir = Path.home() / ".cache" / "whisper"
                    model_file = model_dir / f"ggml-{self._model_size}.bin"

                    if model_file.exists():
                        model_path = str(model_file)
                    else:
                        # Try to use model name directly (whisper-cpp-python may handle download)
                        model_path = self._model_size

                logger.info("Loading Whisper model: %s", model_path)
                self._whisper = Whisper.from_pretrained(model_path)
                self._available = True
                logger.info("Whisper model loaded successfully")

            except ImportError:
                logger.warning("whisper-cpp-python not installed, local STT unavailable")
                self._available = False
            except Exception as e:
                logger.warning("Failed to load Whisper model: %s", e)
                self._available = False

    async def transcribe(
        self,
        audio: bytes,
        language: str = "en",
        sample_rate: int = 16000,
    ) -> str:
        """Transcribe audio using local Whisper."""
        await self._ensure_initialized()

        if not self._available or self._whisper is None:
            raise RuntimeError("Whisper model not available")

        # Write audio to temp file (whisper-cpp expects file path or numpy array)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name
            # Write WAV header + audio data
            self._write_wav(f, audio, sample_rate)

        try:
            # Run transcription in thread pool (Whisper is CPU-bound)
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self._whisper.transcribe(temp_path, language=language),
            )

            # Extract text from result
            if isinstance(result, str):
                return result.strip()
            elif hasattr(result, "text"):
                return result.text.strip()
            elif isinstance(result, dict):
                return result.get("text", "").strip()
            else:
                return str(result).strip()

        finally:
            # Clean up temp file
            try:
                os.unlink(temp_path)
            except OSError:
                pass

    def _write_wav(self, f: io.IOBase, audio: bytes, sample_rate: int) -> None:
        """Write a simple WAV header for 16-bit mono PCM audio."""
        import struct

        num_samples = len(audio) // 2  # 16-bit = 2 bytes per sample
        bits_per_sample = 16
        num_channels = 1
        byte_rate = sample_rate * num_channels * bits_per_sample // 8
        block_align = num_channels * bits_per_sample // 8
        data_size = len(audio)
        file_size = 36 + data_size

        # Write RIFF header
        f.write(b"RIFF")
        f.write(struct.pack("<I", file_size))
        f.write(b"WAVE")

        # Write fmt chunk
        f.write(b"fmt ")
        f.write(struct.pack("<I", 16))  # Chunk size
        f.write(struct.pack("<H", 1))  # Audio format (PCM)
        f.write(struct.pack("<H", num_channels))
        f.write(struct.pack("<I", sample_rate))
        f.write(struct.pack("<I", byte_rate))
        f.write(struct.pack("<H", block_align))
        f.write(struct.pack("<H", bits_per_sample))

        # Write data chunk
        f.write(b"data")
        f.write(struct.pack("<I", data_size))
        f.write(audio)

    def is_available(self) -> bool:
        """Check if Whisper is available (prerequisites met)."""
        return self._can_be_available


class OpenAIWhisperClient(STTProvider):
    """OpenAI Whisper API client for cloud-based transcription."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._client = None

    async def _ensure_client(self) -> None:
        """Lazy initialization of OpenAI client."""
        if self._client is not None:
            return

        try:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(api_key=self._api_key)
        except ImportError:
            raise RuntimeError("openai package not installed")

    async def transcribe(
        self,
        audio: bytes,
        language: str = "en",
        sample_rate: int = 16000,
    ) -> str:
        """Transcribe audio using OpenAI Whisper API."""
        await self._ensure_client()

        if self._client is None:
            raise RuntimeError("OpenAI client not initialized")

        # Create in-memory WAV file
        wav_buffer = io.BytesIO()
        self._write_wav(wav_buffer, audio, sample_rate)
        wav_buffer.seek(0)
        wav_buffer.name = "audio.wav"

        # Call OpenAI API
        response = await self._client.audio.transcriptions.create(
            model="whisper-1",
            file=wav_buffer,
            language=language if language != "auto" else None,
            response_format="text",
        )

        return response.strip() if isinstance(response, str) else str(response).strip()

    def _write_wav(self, f: io.IOBase, audio: bytes, sample_rate: int) -> None:
        """Write a simple WAV header for 16-bit mono PCM audio."""
        import struct

        bits_per_sample = 16
        num_channels = 1
        byte_rate = sample_rate * num_channels * bits_per_sample // 8
        block_align = num_channels * bits_per_sample // 8
        data_size = len(audio)
        file_size = 36 + data_size

        # Write RIFF header
        f.write(b"RIFF")
        f.write(struct.pack("<I", file_size))
        f.write(b"WAVE")

        # Write fmt chunk
        f.write(b"fmt ")
        f.write(struct.pack("<I", 16))
        f.write(struct.pack("<H", 1))
        f.write(struct.pack("<H", num_channels))
        f.write(struct.pack("<I", sample_rate))
        f.write(struct.pack("<I", byte_rate))
        f.write(struct.pack("<H", block_align))
        f.write(struct.pack("<H", bits_per_sample))

        # Write data chunk
        f.write(b"data")
        f.write(struct.pack("<I", data_size))
        f.write(audio)

    def is_available(self) -> bool:
        """Check if API key is configured."""
        return bool(self._api_key)


class HybridSTT:
    """Hybrid STT that tries local Whisper first, falls back to OpenAI.

    This implements the offline-first strategy:
    1. Try local Whisper.cpp (fast, free, private)
    2. Fall back to OpenAI Whisper API (reliable, accurate)
    """

    def __init__(
        self,
        local_model_path: str | None = None,
        local_model_size: str = "base.en",
        openai_api_key: str | None = None,
        prefer_local: bool = True,
    ) -> None:
        self._local = WhisperCppClient(
            model_path=local_model_path,
            model_size=local_model_size,
        )
        self._cloud = OpenAIWhisperClient(api_key=openai_api_key)
        self._prefer_local = prefer_local
        self._local_failures = 0
        self._max_local_failures = 3  # Switch to cloud after N consecutive failures

    def set_prefer_local(self, prefer: bool) -> None:
        """Set preference for local vs cloud STT."""
        self._prefer_local = prefer

    async def transcribe(
        self,
        audio: bytes,
        language: str = "en",
        sample_rate: int = 16000,
        prefer_local: bool | None = None,
    ) -> str:
        """Transcribe audio with automatic fallback.

        Args:
            audio: Raw PCM audio bytes (16-bit, mono)
            language: Language code (e.g., "en", "es", "auto")
            sample_rate: Audio sample rate in Hz
            prefer_local: Override default preference (None uses instance default)

        Returns:
            Transcribed text
        """
        # Use override if provided, otherwise use instance default
        use_local = prefer_local if prefer_local is not None else self._prefer_local
        providers = self._get_provider_order(prefer_local=use_local)

        last_error: Exception | None = None

        for provider in providers:
            try:
                result = await provider.transcribe(
                    audio,
                    language=language,
                    sample_rate=sample_rate,
                )

                # Reset failure counter on success
                if provider is self._local:
                    self._local_failures = 0

                return result

            except Exception as e:
                logger.warning(
                    "STT provider %s failed: %s",
                    provider.__class__.__name__,
                    e,
                )
                last_error = e

                # Track local failures
                if provider is self._local:
                    self._local_failures += 1

        # All providers failed
        raise RuntimeError(
            f"All STT providers failed. Last error: {last_error}"
        ) from last_error

    def _get_provider_order(self, prefer_local: bool | None = None) -> list[STTProvider]:
        """Determine provider order based on preferences and health."""
        want_local = prefer_local if prefer_local is not None else self._prefer_local
        providers: list[STTProvider] = []

        # Check if we should skip local due to repeated failures
        local_healthy = (
            self._local.is_available()
            and self._local_failures < self._max_local_failures
        )
        use_local = want_local and local_healthy

        if use_local:
            providers.append(self._local)

        if self._cloud.is_available():
            providers.append(self._cloud)

        # If explicitly want cloud first, reorder
        if not want_local and self._cloud.is_available():
            providers = [self._cloud]
            if local_healthy:
                providers.append(self._local)

        # If local was skipped but no cloud, try local anyway
        if not providers:
            providers.append(self._local)

        return providers

    def get_status(self) -> dict:
        """Get current STT provider status."""
        return {
            "local_available": self._local.is_available(),
            "cloud_available": self._cloud.is_available(),
            "local_failures": self._local_failures,
            "prefer_local": self._prefer_local,
            "active_provider": (
                "local"
                if self._prefer_local
                and self._local.is_available()
                and self._local_failures < self._max_local_failures
                else "cloud" if self._cloud.is_available() else "none"
            ),
        }
