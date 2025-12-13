# voice/kokoro_manager.py
"""
Singleton manager for Kokoro TTS model with Apple Silicon optimizations.
Adapted from HowdyTTS for KITT voice service.
"""

from __future__ import annotations

import logging
import os
import platform
import sys
import warnings
from pathlib import Path
from typing import Optional

# Set environment variables for ONNX optimization BEFORE importing onnxruntime
os.environ["OMP_NUM_THREADS"] = str(max(1, (os.cpu_count() or 4) - 1))
os.environ["ORT_TENSORRT_FP16_ENABLE"] = "1"

# Enable CoreML on Apple Silicon
if platform.system() == "Darwin" and platform.machine() == "arm64":
    os.environ["ORT_COREML_ALLOWED"] = "1"

logger = logging.getLogger(__name__)

# Lazy-load ONNX runtime
_ort = None


def _get_onnx_runtime():
    """Lazy-load the appropriate ONNX runtime for the platform."""
    global _ort
    if _ort is not None:
        return _ort

    is_apple_silicon = platform.system() == "Darwin" and platform.machine() == "arm64"

    if is_apple_silicon:
        try:
            import onnxruntime_silicon as ort
            logger.info("Using onnxruntime-silicon for Apple Silicon optimizations")
            _ort = ort
        except ImportError:
            try:
                import onnxruntime as ort
                logger.info("onnxruntime-silicon not found, falling back to standard onnxruntime")
                _ort = ort
            except ImportError:
                logger.error("No ONNX Runtime available. Install onnxruntime or onnxruntime-silicon")
                raise ImportError("ONNX Runtime not available")
    else:
        try:
            import onnxruntime as ort
            logger.info("Using standard onnxruntime")
            _ort = ort
        except ImportError:
            logger.error("ONNX Runtime not available. Install onnxruntime")
            raise ImportError("ONNX Runtime not available")

    return _ort


class KokoroManager:
    """
    Singleton manager for the Kokoro TTS model.

    Handles lazy initialization, Apple Silicon optimizations, and resource cleanup.
    """

    _instance: Optional["KokoroManager"] = None
    _kokoro = None
    _initialized: bool = False

    def __new__(cls) -> "KokoroManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def get_instance(
        cls,
        model_path: Optional[str] = None,
        voices_path: Optional[str] = None,
    ) -> "KokoroManager":
        """
        Get or initialize the Kokoro manager singleton.

        Args:
            model_path: Path to kokoro-v1.0.onnx model file
            voices_path: Path to voices-v1.0.bin file

        Returns:
            KokoroManager singleton instance
        """
        instance = cls()
        if not cls._initialized:
            instance._initialize(model_path, voices_path)
        return instance

    def _initialize(
        self,
        model_path: Optional[str] = None,
        voices_path: Optional[str] = None,
    ) -> None:
        """Initialize the Kokoro model with optimization settings."""
        logger.info("Initializing Kokoro TTS model...")

        # Resolve model paths from environment or defaults
        model_path = self._resolve_path(
            model_path,
            os.getenv("KOKORO_MODEL_PATH"),
            "~/.local/share/kitty/models/kokoro-v1.0.onnx",
        )
        voices_path = self._resolve_path(
            voices_path,
            os.getenv("KOKORO_VOICES_PATH"),
            "~/.local/share/kitty/models/voices-v1.0.bin",
        )

        # Verify files exist
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Kokoro model not found: {model_path}")
        if not os.path.exists(voices_path):
            raise FileNotFoundError(f"Kokoro voices not found: {voices_path}")

        logger.info(f"Loading Kokoro model from: {model_path}")
        logger.info(f"Loading Kokoro voices from: {voices_path}")

        # Get ONNX runtime and configure
        ort = _get_onnx_runtime()
        self._log_platform_info(ort)

        # Set ONNX logging level
        try:
            ort.set_default_logger_severity(3)  # Warning level
        except Exception:
            pass

        # Import and initialize Kokoro
        try:
            from kokoro_onnx import Kokoro
        except ImportError:
            raise ImportError("kokoro-onnx not installed. Run: pip install kokoro-onnx>=0.4.0")

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=UserWarning)
            self.__class__._kokoro = Kokoro(model_path, voices_path)

        # Preload default voice
        default_voice = os.getenv("KOKORO_DEFAULT_VOICE", "am_michael")
        self._preload_voice(default_voice)

        self.__class__._initialized = True
        logger.info("Kokoro TTS model initialized successfully")

    def _resolve_path(self, *candidates: Optional[str]) -> str:
        """Resolve the first valid path from candidates."""
        for path in candidates:
            if path:
                expanded = os.path.expanduser(path)
                return expanded
        raise ValueError("No valid path provided")

    def _log_platform_info(self, ort) -> None:
        """Log platform and provider information."""
        system = platform.system()
        machine = platform.machine()
        logger.info(f"Platform: {system} ({machine})")

        if hasattr(ort, "get_available_providers"):
            providers = ort.get_available_providers()
            logger.info(f"Available ONNX providers: {providers}")
            if system == "Darwin" and machine == "arm64":
                if "CoreMLExecutionProvider" in providers:
                    logger.info("CoreML provider available for Apple Silicon")
        else:
            logger.info("Cannot query ONNX providers")

    def _preload_voice(self, voice: str) -> None:
        """Preload a voice model to warm up inference."""
        if self._kokoro is None:
            return
        try:
            _ = self._kokoro.create("Hello.", voice=voice, speed=1.0, lang="en-us")
            logger.info(f"Preloaded voice: {voice}")
        except Exception as e:
            logger.warning(f"Failed to preload voice {voice}: {e}")

    @property
    def kokoro(self):
        """Get the underlying Kokoro model instance."""
        if not self._initialized or self._kokoro is None:
            raise RuntimeError("KokoroManager not initialized. Call get_instance() first.")
        return self._kokoro

    def create(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: float = 1.0,
        lang: str = "en-us",
    ) -> tuple:
        """
        Generate speech from text.

        Args:
            text: Text to synthesize
            voice: Voice model to use (default from env)
            speed: Speech speed multiplier
            lang: Language code

        Returns:
            Tuple of (samples: np.ndarray, sample_rate: int)
        """
        if voice is None:
            voice = os.getenv("KOKORO_DEFAULT_VOICE", "am_michael")

        return self.kokoro.create(text, voice=voice, speed=speed, lang=lang)

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton, forcing reinitialization on next use."""
        cls._kokoro = None
        cls._initialized = False
        cls._instance = None
        logger.info("KokoroManager reset")

    @classmethod
    def is_available(cls) -> bool:
        """Check if Kokoro TTS is available (dependencies installed)."""
        try:
            _get_onnx_runtime()
            from kokoro_onnx import Kokoro
            return True
        except ImportError:
            return False


# Module-level convenience function
def get_kokoro() -> KokoroManager:
    """Get the Kokoro manager singleton."""
    return KokoroManager.get_instance()
