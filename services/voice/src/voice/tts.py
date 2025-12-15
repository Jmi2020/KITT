"""Streaming Text-to-Speech with local Kokoro/Piper and OpenAI fallback.

Supports real-time audio generation as text arrives,
with sentence-level buffering for natural speech flow.

Provider priority (configurable via LOCAL_TTS_PROVIDER env):
1. Kokoro ONNX - Apple Silicon optimized (default)
2. Piper - CPU-based fallback
3. OpenAI - Cloud fallback
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import re
import subprocess
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import AsyncIterator, Optional

import numpy as np

logger = logging.getLogger(__name__)


class TTSProvider(ABC):
    """Abstract base class for TTS providers."""

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        voice: str = "default",
    ) -> bytes:
        """Synthesize text to audio bytes (PCM 16-bit mono)."""
        ...

    @abstractmethod
    async def synthesize_stream(
        self,
        text: str,
        voice: str = "default",
    ) -> AsyncIterator[bytes]:
        """Stream audio chunks as they're generated."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is available."""
        ...

    @abstractmethod
    def get_voices(self) -> list[str]:
        """Get available voice names."""
        ...


class PiperTTSClient(TTSProvider):
    """Local Piper TTS client for offline speech synthesis.

    Piper is a fast, local neural TTS engine that runs on CPU.
    https://github.com/rhasspy/piper
    """

    # Map friendly voice names to Piper model names
    # Maps OpenAI voice names to local Piper models
    VOICE_MAP = {
        "default": "en_US-amy-medium",
        "alloy": "en_US-amy-medium",
        "echo": "en_US-ryan-medium",
        "fable": "en_US-ryan-medium",
        "onyx": "en_US-ryan-medium",
        "nova": "en_US-amy-medium",
        "shimmer": "en_US-amy-medium",
    }

    def __init__(
        self,
        model_dir: str | None = None,
        sample_rate: int = 16000,
    ) -> None:
        self._model_dir = Path(model_dir) if model_dir else Path.home() / ".local" / "share" / "piper"
        self._sample_rate = sample_rate
        self._available = False
        self._piper_path: str | None = None
        self._check_availability()

    def _check_availability(self) -> None:
        """Check if Piper is installed and has models available."""
        try:
            import sys

            # Check paths where piper might be
            candidate_paths = [
                # Current Python environment's bin
                str(Path(sys.executable).parent / "piper"),
                # System paths
                "/usr/local/bin/piper",
                "/opt/homebrew/bin/piper",
                str(Path.home() / ".local" / "bin" / "piper"),
            ]

            # Try to find piper executable
            for path in candidate_paths:
                if Path(path).exists():
                    self._piper_path = path
                    logger.info("Found Piper executable at: %s", self._piper_path)
                    break
            else:
                # Last resort: use `which`
                result = subprocess.run(
                    ["which", "piper"],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    self._piper_path = result.stdout.strip()
                    logger.info("Found Piper via which: %s", self._piper_path)

            if not self._piper_path:
                logger.warning("Piper executable not found")
                self._available = False
                return

            # Check if we have any model files
            if self._model_dir.exists():
                models = list(self._model_dir.glob("*.onnx"))
                if models:
                    self._available = True
                    logger.info(
                        "Piper TTS available: %d models in %s",
                        len(models),
                        self._model_dir,
                    )
                else:
                    logger.warning("Piper found but no .onnx models in %s", self._model_dir)
                    self._available = False
            else:
                logger.warning("Piper model directory does not exist: %s", self._model_dir)
                self._available = False

        except Exception as e:
            logger.warning("Failed to check Piper availability: %s", e)
            self._available = False

    def _get_model_path(self, voice: str) -> str:
        """Get the model path for a voice."""
        model_name = self.VOICE_MAP.get(voice, voice)

        # Check for model file
        model_path = self._model_dir / f"{model_name}.onnx"
        if model_path.exists():
            return str(model_path)

        # Try with .onnx.json config file
        config_path = self._model_dir / f"{model_name}.onnx.json"
        if config_path.exists():
            return str(self._model_dir / f"{model_name}.onnx")

        # Return the model name and let Piper handle downloading
        return model_name

    async def synthesize(
        self,
        text: str,
        voice: str = "default",
    ) -> bytes:
        """Synthesize text to audio bytes."""
        if not self._available:
            raise RuntimeError("Piper TTS not available")

        model_path = self._get_model_path(voice)

        # Create temp output file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            output_path = f.name

        try:
            # Run Piper
            process = await asyncio.create_subprocess_exec(
                self._piper_path,
                "--model", model_path,
                "--output_file", output_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate(text.encode("utf-8"))

            if process.returncode != 0:
                raise RuntimeError(f"Piper failed: {stderr.decode()}")

            # Read and return audio data (skip WAV header for raw PCM)
            with open(output_path, "rb") as f:
                wav_data = f.read()
                # Skip 44-byte WAV header
                return wav_data[44:]

        finally:
            try:
                os.unlink(output_path)
            except OSError:
                pass

    async def synthesize_stream(
        self,
        text: str,
        voice: str = "default",
    ) -> AsyncIterator[bytes]:
        """Stream audio chunks.

        Note: Piper doesn't support true streaming, so we synthesize
        sentence by sentence for a streaming-like experience.
        """
        # Split into sentences for pseudo-streaming
        sentences = self._split_sentences(text)

        for sentence in sentences:
            if sentence.strip():
                audio = await self.synthesize(sentence, voice)
                yield audio

    def _split_sentences(self, text: str) -> list[str]:
        """Split text into sentences."""
        # Simple sentence splitting
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]

    def is_available(self) -> bool:
        """Check if Piper is available."""
        return self._available

    def get_voices(self) -> list[str]:
        """Get available voice names."""
        return list(self.VOICE_MAP.keys())


class KokoroTTSClient(TTSProvider):
    """Kokoro ONNX TTS client optimized for Apple Silicon.

    Provides high-quality neural TTS with adaptive chunking
    for smooth playback on longer texts.
    """

    # Map OpenAI voice names to Kokoro voices
    VOICE_MAP = {
        "default": "am_michael",
        "alloy": "am_michael",
        "echo": "am_michael",
        "fable": "af",  # Female voice
        "onyx": "am_michael",
        "nova": "af",
        "shimmer": "af",
    }

    def __init__(
        self,
        default_voice: str | None = None,
        speed: float | None = None,
    ) -> None:
        self._default_voice = default_voice or os.getenv("KOKORO_DEFAULT_VOICE", "am_michael")
        self._speed = speed or float(os.getenv("KOKORO_SPEED", "1.0"))
        self._available = False
        self._tts = None
        self._check_availability()

    def _check_availability(self) -> None:
        """Check if Kokoro dependencies are available."""
        try:
            from .kokoro_manager import KokoroManager

            if KokoroManager.is_available():
                # Check model files exist
                model_path = os.path.expanduser(
                    os.getenv("KOKORO_MODEL_PATH", "~/.local/share/kitty/models/kokoro-v1.0.onnx")
                )
                if os.path.exists(model_path):
                    self._available = True
                    logger.info("Kokoro TTS available with model: %s", model_path)
                else:
                    logger.warning("Kokoro model not found: %s", model_path)
                    self._available = False
            else:
                logger.info("Kokoro dependencies not available")
                self._available = False
        except ImportError as e:
            logger.info("Kokoro not available: %s", e)
            self._available = False
        except Exception as e:
            logger.warning("Error checking Kokoro availability: %s", e)
            self._available = False

    def _ensure_tts(self) -> None:
        """Lazy initialization of Kokoro TTS."""
        if self._tts is not None:
            return

        from .kokoro_tts import KokoroTTS

        self._tts = KokoroTTS(
            voice=self._default_voice,
            speed=self._speed,
        )

    def _get_voice(self, voice: str) -> str:
        """Map voice name to Kokoro voice."""
        # Use configured default voice for "default", otherwise check voice map
        if voice == "default":
            return self._default_voice
        return self.VOICE_MAP.get(voice, self._default_voice)

    async def synthesize(
        self,
        text: str,
        voice: str = "default",
    ) -> bytes:
        """Synthesize text to audio bytes."""
        if not self._available:
            raise RuntimeError("Kokoro TTS not available")

        self._ensure_tts()

        if self._tts is None:
            raise RuntimeError("Kokoro TTS initialization failed")

        # Set voice temporarily
        original_voice = self._tts.voice
        self._tts.voice = self._get_voice(voice)

        try:
            samples, sample_rate = self._tts.synthesize(text)

            # Convert float32 samples to int16 PCM bytes
            pcm_samples = (samples * 32767).astype(np.int16)
            return pcm_samples.tobytes()

        finally:
            self._tts.voice = original_voice

    async def synthesize_stream(
        self,
        text: str,
        voice: str = "default",
    ) -> AsyncIterator[bytes]:
        """Stream audio chunks using adaptive chunking."""
        if not self._available:
            raise RuntimeError("Kokoro TTS not available")

        self._ensure_tts()

        if self._tts is None:
            raise RuntimeError("Kokoro TTS initialization failed")

        # Set voice temporarily
        original_voice = self._tts.voice
        resolved_voice = self._get_voice(voice)
        print(f"[Kokoro] Voice: requested={voice}, resolved={resolved_voice}, default={self._default_voice}", flush=True)
        self._tts.voice = resolved_voice

        try:
            async for chunk in self._tts.synthesize_streaming(text):
                # Convert float32 samples to int16 PCM bytes
                pcm_samples = (chunk.samples * 32767).astype(np.int16)
                yield pcm_samples.tobytes()

        finally:
            self._tts.voice = original_voice

    def is_available(self) -> bool:
        """Check if Kokoro is available."""
        return self._available

    def get_voices(self) -> list[str]:
        """Get available voice names."""
        return list(self.VOICE_MAP.keys())


class OpenAITTSClient(TTSProvider):
    """OpenAI TTS API client for cloud-based speech synthesis."""

    VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "tts-1",
    ) -> None:
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._model = model
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

    async def synthesize(
        self,
        text: str,
        voice: str = "alloy",
    ) -> bytes:
        """Synthesize text using OpenAI TTS API."""
        await self._ensure_client()

        if self._client is None:
            raise RuntimeError("OpenAI client not initialized")

        # Map voice name if needed
        if voice not in self.VOICES:
            voice = "alloy"

        response = await self._client.audio.speech.create(
            model=self._model,
            voice=voice,
            input=text,
            response_format="pcm",  # Raw 24kHz 16-bit mono PCM
        )

        # Read response content
        audio_data = response.content

        # Resample from 24kHz to 16kHz if needed
        # For now, return as-is (client can handle resampling)
        return audio_data

    async def synthesize_stream(
        self,
        text: str,
        voice: str = "alloy",
    ) -> AsyncIterator[bytes]:
        """Stream audio from OpenAI TTS.

        OpenAI TTS supports streaming via response chunks.
        """
        await self._ensure_client()

        if self._client is None:
            raise RuntimeError("OpenAI client not initialized")

        if voice not in self.VOICES:
            voice = "alloy"

        # Use streaming response
        async with self._client.audio.speech.with_streaming_response.create(
            model=self._model,
            voice=voice,
            input=text,
            response_format="pcm",
        ) as response:
            async for chunk in response.iter_bytes(chunk_size=4096):
                yield chunk

    def is_available(self) -> bool:
        """Check if API key is configured."""
        return bool(self._api_key)

    def get_voices(self) -> list[str]:
        """Get available voice names."""
        return self.VOICES


class StreamingTTS:
    """Hybrid streaming TTS with Kokoro/Piper local and OpenAI cloud fallback.

    Provider selection order (configurable via LOCAL_TTS_PROVIDER env):
    - kokoro: Kokoro ONNX (Apple Silicon optimized) -> Piper -> OpenAI
    - piper: Piper -> Kokoro -> OpenAI
    - openai: OpenAI only (cloud)
    """

    def __init__(
        self,
        piper_model_dir: str | None = None,
        openai_api_key: str | None = None,
        openai_model: str = "tts-1",
        prefer_local: bool = True,
        local_provider: str | None = None,
    ) -> None:
        # Determine local provider preference
        self._local_provider = local_provider or os.getenv("LOCAL_TTS_PROVIDER", "kokoro")

        # Initialize all providers
        self._kokoro = KokoroTTSClient()
        self._piper = PiperTTSClient(model_dir=piper_model_dir)
        self._cloud = OpenAITTSClient(api_key=openai_api_key, model=openai_model)

        self._prefer_local = prefer_local
        self._kokoro_failures = 0
        self._piper_failures = 0
        self._max_local_failures = 3

        # Log provider status
        logger.info(
            "TTS initialized: kokoro=%s, piper=%s, cloud=%s, preferred=%s",
            self._kokoro.is_available(),
            self._piper.is_available(),
            self._cloud.is_available(),
            self._local_provider,
        )

    def _strip_markdown(self, text: str) -> str:
        """Remove markdown formatting for clean TTS output.

        Strips characters like *, #, backticks, etc. that would otherwise
        be spoken aloud by the TTS engine.
        """
        # Remove code blocks (```...```)
        text = re.sub(r'```[\s\S]*?```', '', text)

        # Remove inline code (`...`)
        text = re.sub(r'`([^`]+)`', r'\1', text)

        # Remove bold (**text** or __text__)
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
        text = re.sub(r'__([^_]+)__', r'\1', text)

        # Remove italic (*text* or _text_)
        text = re.sub(r'\*([^*]+)\*', r'\1', text)
        text = re.sub(r'(?<!\w)_([^_]+)_(?!\w)', r'\1', text)

        # Remove headers (# ## ### etc.)
        text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)

        # Remove links [text](url) -> text
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)

        # Remove images ![alt](url)
        text = re.sub(r'!\[([^\]]*)\]\([^)]+\)', r'\1', text)

        # Remove horizontal rules (---, ***, ___)
        text = re.sub(r'^[\-\*_]{3,}\s*$', '', text, flags=re.MULTILINE)

        # Remove bullet points (- or * at start of line)
        text = re.sub(r'^\s*[\-\*]\s+', '', text, flags=re.MULTILINE)

        # Remove numbered lists (1. 2. etc.)
        text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)

        # Remove blockquotes (>)
        text = re.sub(r'^\s*>\s*', '', text, flags=re.MULTILINE)

        # Clean up extra whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = text.strip()

        return text

    async def synthesize(
        self,
        text: str,
        voice: str = "alloy",
    ) -> bytes:
        """Synthesize text to audio with automatic fallback."""
        # Strip markdown formatting before TTS
        text = self._strip_markdown(text)

        providers = self._get_provider_order()

        last_error: Exception | None = None

        for provider in providers:
            try:
                result = await provider.synthesize(text, voice)
                self._reset_failures(provider)
                return result

            except Exception as e:
                logger.warning(
                    "TTS provider %s failed: %s",
                    provider.__class__.__name__,
                    e,
                )
                last_error = e
                self._track_failure(provider)

        raise RuntimeError(
            f"All TTS providers failed. Last error: {last_error}"
        ) from last_error

    async def synthesize_stream(
        self,
        text: str,
        voice: str = "alloy",
    ) -> AsyncIterator[bytes]:
        """Stream audio chunks with automatic fallback."""
        # Strip markdown formatting before TTS
        text = self._strip_markdown(text)

        providers = self._get_provider_order()

        for provider in providers:
            try:
                async for chunk in provider.synthesize_stream(text, voice):
                    yield chunk

                self._reset_failures(provider)
                return  # Success, don't try other providers

            except Exception as e:
                logger.warning(
                    "TTS provider %s failed: %s",
                    provider.__class__.__name__,
                    e,
                )
                self._track_failure(provider)
                continue  # Try next provider

        # All providers failed - raise error
        raise RuntimeError("All TTS providers failed")

    async def synthesize_text_stream(
        self,
        text_stream: AsyncIterator[str],
        voice: str = "alloy",
    ) -> AsyncIterator[bytes]:
        """Synthesize audio from streaming text input.

        Buffers text until complete sentences are available,
        then synthesizes and yields audio chunks.
        """
        buffer = ""
        sentence_pattern = re.compile(r'([.!?])\s*')

        async for text_chunk in text_stream:
            buffer += text_chunk

            # Check for complete sentences
            while True:
                match = sentence_pattern.search(buffer)
                if not match:
                    break

                # Extract complete sentence
                end_pos = match.end()
                sentence = buffer[:end_pos].strip()
                buffer = buffer[end_pos:]

                if sentence:
                    async for audio_chunk in self.synthesize_stream(sentence, voice):
                        yield audio_chunk

        # Handle remaining text
        if buffer.strip():
            async for audio_chunk in self.synthesize_stream(buffer.strip(), voice):
                yield audio_chunk

    def _get_provider_order(self) -> list[TTSProvider]:
        """Determine provider order based on preferences and health."""
        providers: list[TTSProvider] = []

        if not self._prefer_local:
            # Cloud-only mode
            if self._cloud.is_available():
                providers.append(self._cloud)
            return providers

        # Build local provider chain based on preference
        if self._local_provider == "kokoro":
            # Kokoro -> Piper -> Cloud
            if self._kokoro.is_available() and self._kokoro_failures < self._max_local_failures:
                providers.append(self._kokoro)
            if self._piper.is_available() and self._piper_failures < self._max_local_failures:
                providers.append(self._piper)
        elif self._local_provider == "piper":
            # Piper -> Kokoro -> Cloud
            if self._piper.is_available() and self._piper_failures < self._max_local_failures:
                providers.append(self._piper)
            if self._kokoro.is_available() and self._kokoro_failures < self._max_local_failures:
                providers.append(self._kokoro)
        # openai mode or fallback
        if self._cloud.is_available():
            providers.append(self._cloud)

        return providers

    def _track_failure(self, provider: TTSProvider) -> None:
        """Track provider failures."""
        if provider is self._kokoro:
            self._kokoro_failures += 1
        elif provider is self._piper:
            self._piper_failures += 1

    def _reset_failures(self, provider: TTSProvider) -> None:
        """Reset failure count on success."""
        if provider is self._kokoro:
            self._kokoro_failures = 0
        elif provider is self._piper:
            self._piper_failures = 0

    def get_voices(self) -> list[str]:
        """Get available voices from active provider."""
        # Try providers in order of preference
        for provider in self._get_provider_order():
            if provider.is_available():
                return provider.get_voices()
        return ["alloy"]

    def get_active_provider(self) -> str:
        """Get the name of the currently active provider."""
        providers = self._get_provider_order()
        if not providers:
            return "none"

        provider = providers[0]
        if provider is self._kokoro:
            return "kokoro"
        elif provider is self._piper:
            return "piper"
        elif provider is self._cloud:
            return "openai"
        return "unknown"

    def get_status(self) -> dict:
        """Get current TTS provider status."""
        return {
            "kokoro_available": self._kokoro.is_available(),
            "piper_available": self._piper.is_available(),
            "cloud_available": self._cloud.is_available(),
            "kokoro_failures": self._kokoro_failures,
            "piper_failures": self._piper_failures,
            "prefer_local": self._prefer_local,
            "local_provider": self._local_provider,
            "active_provider": self.get_active_provider(),
            "voices": self.get_voices(),
        }
