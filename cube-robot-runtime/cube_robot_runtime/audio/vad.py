"""Small local voice-activity detector for trigger probes."""

from __future__ import annotations

import io
import math
import wave
from array import array


def has_voice(audio: bytes, *, threshold: float = 0.02) -> bool:
    """Return whether a WAV or raw 16-bit PCM probe is likely speech.

    The runtime only needs a cheap local trigger before sending a full turn to
    the server, so RMS energy is enough for this first pass.
    """
    if threshold <= 0:
        raise ValueError("threshold must be positive")
    samples = _pcm16_samples(audio)
    if not samples:
        return False
    rms = math.sqrt(sum((sample / 32768.0) ** 2 for sample in samples) / len(samples))
    return rms >= threshold


def _pcm16_samples(audio: bytes) -> tuple[int, ...]:
    try:
        with wave.open(io.BytesIO(audio), "rb") as wav:
            if wav.getsampwidth() != 2:
                raise ValueError("only 16-bit PCM WAV is supported")
            frames = wav.readframes(wav.getnframes())
    except (EOFError, wave.Error):
        frames = audio
    return _samples_from_frames(frames)


def _samples_from_frames(frames: bytes) -> tuple[int, ...]:
    if len(frames) < 2:
        return ()
    usable = frames[: len(frames) - (len(frames) % 2)]
    samples = array("h")
    samples.frombytes(usable)
    if samples.itemsize != 2:
        raise RuntimeError("platform does not expose 16-bit short samples")
    return tuple(samples)
