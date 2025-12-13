# voice/wake_word.py
"""
Wake word detection using Picovoice Porcupine.
Enables hands-free activation with custom wake words.
"""

from __future__ import annotations

import gc
import logging
import os
import queue
import struct
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Registry for cleanup management
_DETECTOR_REGISTRY: list["WakeWordDetector"] = []
_MAX_DETECTORS = 3


def cleanup_all_detectors() -> None:
    """Force cleanup of all detector instances."""
    for detector in list(_DETECTOR_REGISTRY):
        try:
            detector.cleanup(force=True)
        except Exception:
            pass
    _DETECTOR_REGISTRY.clear()
    gc.collect()


class WakeWordDetector:
    """
    Wake word detection using Porcupine by Picovoice.

    Listens for a custom wake word and triggers a callback when detected.
    Runs in a background thread for non-blocking operation.
    """

    def __init__(
        self,
        callback: Callable[[], None],
        sensitivity: float = 0.5,
        model_path: Optional[str] = None,
    ):
        """
        Initialize the wake word detector.

        Args:
            callback: Function to call when wake word is detected
            sensitivity: Detection sensitivity 0-1 (higher = more sensitive)
            model_path: Path to custom .ppn wake word model
        """
        self.callback = callback
        self.sensitivity = max(0.0, min(1.0, sensitivity))
        self.porcupine = None
        self.audio = None
        self.audio_stream = None
        self.is_running = False
        self._stop_event = threading.Event()
        self._detection_thread: Optional[threading.Thread] = None
        self._callback_thread: Optional[threading.Thread] = None
        self._detection_queue: queue.Queue = queue.Queue()

        # Register for cleanup
        _DETECTOR_REGISTRY.append(self)
        self._cleanup_old_instances()

        # Get Porcupine access key
        access_key = os.getenv("PORCUPINE_ACCESS_KEY")
        if not access_key:
            raise ValueError(
                "PORCUPINE_ACCESS_KEY not set. "
                "Get your key at https://console.picovoice.ai/"
            )

        # Resolve model path
        model_path = self._resolve_model_path(model_path)

        # Initialize Porcupine
        self._init_porcupine(access_key, model_path)

        # Initialize PyAudio
        self._init_audio()

    def _cleanup_old_instances(self) -> None:
        """Remove old instances to prevent resource leaks."""
        while len(_DETECTOR_REGISTRY) > _MAX_DETECTORS:
            old = _DETECTOR_REGISTRY.pop(0)
            if old != self:
                try:
                    old.cleanup(force=True)
                except Exception:
                    pass

    def _resolve_model_path(self, model_path: Optional[str]) -> str:
        """Resolve the wake word model path."""
        if model_path:
            path = os.path.expanduser(model_path)
            if os.path.exists(path):
                return path

        # Try environment variable
        env_path = os.getenv("WAKE_WORD_MODEL_PATH")
        if env_path:
            path = os.path.expanduser(env_path)
            if os.path.exists(path):
                logger.info(f"Using wake word model from env: {path}")
                return path

        # Default location
        default_path = os.path.expanduser(
            "~/.local/share/kitty/models/Hey-Howdy_en_mac_v3_0_0.ppn"
        )
        if os.path.exists(default_path):
            logger.info(f"Using default wake word model: {default_path}")
            return default_path

        raise FileNotFoundError(
            "Wake word model not found. Set WAKE_WORD_MODEL_PATH or place model at "
            "~/.local/share/kitty/models/Hey-Howdy_en_mac_v3_0_0.ppn"
        )

    def _init_porcupine(self, access_key: str, model_path: str) -> None:
        """Initialize the Porcupine engine."""
        try:
            import pvporcupine

            logger.info(f"Initializing Porcupine with model: {model_path}")
            self.porcupine = pvporcupine.create(
                access_key=access_key,
                keyword_paths=[model_path],
                sensitivities=[self.sensitivity],
            )
            logger.info("Porcupine initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Porcupine: {e}")
            raise

    def _init_audio(self) -> None:
        """Initialize PyAudio."""
        try:
            import pyaudio

            self.audio = pyaudio.PyAudio()
            logger.debug("PyAudio initialized")
        except Exception as e:
            logger.error(f"Failed to initialize PyAudio: {e}")
            raise

    def start(self) -> None:
        """Start listening for the wake word."""
        if self.is_running:
            logger.warning("Wake word detector already running")
            return

        self.is_running = True
        self._stop_event.clear()

        # Start detection thread
        self._detection_thread = threading.Thread(
            target=self._detection_worker,
            daemon=True,
        )
        self._detection_thread.start()

        # Start callback thread
        self._callback_thread = threading.Thread(
            target=self._callback_worker,
            daemon=True,
        )
        self._callback_thread.start()

        logger.info("Wake word detector started - listening for activation...")

    def stop(self) -> None:
        """Stop the wake word detector."""
        logger.info("Stopping wake word detector...")
        self.is_running = False
        self._stop_event.set()
        time.sleep(0.2)  # Allow threads to terminate
        self.cleanup(force=False)

    def _detection_worker(self) -> None:
        """Background thread for audio processing."""
        import pyaudio

        try:
            self.audio_stream = self.audio.open(
                rate=self.porcupine.sample_rate,
                channels=1,
                format=pyaudio.paInt16,
                input=True,
                frames_per_buffer=self.porcupine.frame_length,
            )

            logger.debug(f"Audio stream opened: {self.porcupine.sample_rate}Hz")

            while not self._stop_event.is_set():
                try:
                    pcm = self.audio_stream.read(
                        self.porcupine.frame_length,
                        exception_on_overflow=False,
                    )
                    pcm = struct.unpack_from(
                        "h" * self.porcupine.frame_length, pcm
                    )

                    keyword_index = self.porcupine.process(pcm)

                    if keyword_index >= 0:
                        logger.info("Wake word detected!")
                        self._detection_queue.put(True)
                        time.sleep(0.5)  # Debounce

                except Exception as e:
                    if not self._stop_event.is_set():
                        logger.error(f"Audio processing error: {e}")
                    time.sleep(0.1)

        except Exception as e:
            logger.error(f"Detection worker error: {e}")
        finally:
            self._cleanup_stream()

    def _callback_worker(self) -> None:
        """Background thread for handling detection callbacks."""
        while self.is_running and not self._stop_event.is_set():
            try:
                detected = self._detection_queue.get(timeout=0.5)
                if detected and self.callback:
                    try:
                        self.callback()
                    except Exception as e:
                        logger.error(f"Callback error: {e}")
            except queue.Empty:
                pass
            except Exception as e:
                logger.error(f"Callback worker error: {e}")
                time.sleep(0.1)

    def _cleanup_stream(self) -> None:
        """Clean up audio stream."""
        if self.audio_stream is not None:
            try:
                self.audio_stream.stop_stream()
                self.audio_stream.close()
                self.audio_stream = None
                logger.debug("Audio stream closed")
            except Exception as e:
                logger.error(f"Error closing audio stream: {e}")

    def cleanup(self, force: bool = False) -> None:
        """Clean up all resources."""
        self._cleanup_stream()

        # Clean up Porcupine
        if self.porcupine is not None:
            try:
                self.porcupine.delete()
                self.porcupine = None
                logger.debug("Porcupine cleaned up")
            except Exception as e:
                logger.error(f"Error cleaning up Porcupine: {e}")

        # Clean up PyAudio
        active_detectors = [
            d for d in _DETECTOR_REGISTRY
            if d != self and d.is_running
        ]
        if force or not active_detectors:
            if self.audio is not None:
                try:
                    self.audio.terminate()
                    self.audio = None
                    logger.debug("PyAudio terminated")
                except Exception as e:
                    logger.error(f"Error terminating PyAudio: {e}")

        # Remove from registry
        if self in _DETECTOR_REGISTRY:
            _DETECTOR_REGISTRY.remove(self)

        gc.collect()
        logger.info("Wake word detector cleaned up")

    def __del__(self):
        """Clean up on deletion."""
        try:
            self.cleanup(force=True)
        except Exception:
            pass


class WakeWordManager:
    """
    Manager for wake word detection lifecycle.

    Handles enabling/disabling wake word detection based on configuration.
    """

    def __init__(self):
        self._detector: Optional[WakeWordDetector] = None
        self._enabled = os.getenv("WAKE_WORD_ENABLED", "false").lower() == "true"

    @property
    def enabled(self) -> bool:
        """Check if wake word detection is enabled."""
        return self._enabled

    @property
    def active(self) -> bool:
        """Check if detector is currently running."""
        return self._detector is not None and self._detector.is_running

    def start(self, callback: Callable[[], None]) -> bool:
        """
        Start wake word detection.

        Args:
            callback: Function to call on detection

        Returns:
            True if started successfully
        """
        if not self._enabled:
            logger.info("Wake word detection disabled")
            return False

        if self.active:
            logger.warning("Wake word detection already active")
            return True

        try:
            sensitivity = float(os.getenv("WAKE_WORD_SENSITIVITY", "0.5"))
            self._detector = WakeWordDetector(callback, sensitivity=sensitivity)
            self._detector.start()
            return True
        except Exception as e:
            logger.error(f"Failed to start wake word detection: {e}")
            return False

    def stop(self) -> None:
        """Stop wake word detection."""
        if self._detector is not None:
            self._detector.stop()
            self._detector = None

    def toggle(self, callback: Callable[[], None]) -> bool:
        """Toggle wake word detection on/off."""
        if self.active:
            self.stop()
            return False
        else:
            return self.start(callback)


# Convenience function
def is_wake_word_available() -> bool:
    """Check if wake word detection is available."""
    try:
        import pvporcupine
        import pyaudio
        return os.getenv("PORCUPINE_ACCESS_KEY") is not None
    except ImportError:
        return False
