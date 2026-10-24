"""Microphone recording and WAV encoding."""

from __future__ import annotations

import io
import threading
import wave
from typing import List

import numpy as np

# Whisper works at 16 kHz mono, so recording at that rate keeps uploads small (~32 KB/s).
SAMPLE_RATE = 16000


def to_wav(samples: np.ndarray, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Encode float samples in [-1, 1] as 16-bit mono WAV."""
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())
    return buffer.getvalue()


def is_silent(samples: np.ndarray, threshold: float = 0.01) -> bool:
    """True when the recording has no speech-level sound (Whisper invents text for silence)."""
    if samples.size == 0:
        return True
    return float(np.sqrt(np.mean(samples**2))) < threshold


class Recorder:
    def __init__(self, sample_rate: int = SAMPLE_RATE):
        self.sample_rate = sample_rate
        self._chunks: List[np.ndarray] = []
        self._lock = threading.Lock()
        self._stream = None

    def _callback(self, indata, frames, time, status):
        with self._lock:
            self._chunks.append(indata[:, 0].copy())

    def start(self) -> None:
        import sounddevice as sd

        with self._lock:
            self._chunks = []
        self._stream = sd.InputStream(
            samplerate=self.sample_rate, channels=1, dtype="float32", callback=self._callback
        )
        self._stream.start()

    def stop(self) -> np.ndarray:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        with self._lock:
            chunks, self._chunks = self._chunks, []
        if not chunks:
            return np.zeros(0, dtype="float32")
        return np.concatenate(chunks)
