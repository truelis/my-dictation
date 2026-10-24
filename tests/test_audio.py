import io
import wave

import numpy as np

from dictation.audio import SAMPLE_RATE, is_silent, to_wav


def test_to_wav_is_16_bit_mono():
    samples = np.sin(np.linspace(0, 100, SAMPLE_RATE)).astype("float32")
    with wave.open(io.BytesIO(to_wav(samples))) as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.getframerate() == SAMPLE_RATE
        assert wav.getnframes() == SAMPLE_RATE


def test_to_wav_clips_loud_samples():
    data = to_wav(np.array([2.0, -2.0], dtype="float32"))
    with wave.open(io.BytesIO(data)) as wav:
        pcm = np.frombuffer(wav.readframes(2), dtype="<i2")
    assert list(pcm) == [32767, -32767]


def test_is_silent():
    assert is_silent(np.zeros(0, dtype="float32"))
    assert is_silent(np.full(1000, 0.001, dtype="float32"))
    assert not is_silent(np.full(1000, 0.2, dtype="float32"))
