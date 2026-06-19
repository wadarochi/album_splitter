"""Test configuration and fixtures for cue-finder."""

import os
import struct
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_dir():
    """Temporary directory that is cleaned up after test."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


def _create_synthetic_wav(path: Path, sample_rate: int, channels: int, duration_sec: float, silence_gaps: list[tuple[float, float]]):
    """Create a synthetic WAV file with silence gaps.

    Args:
        path: Output file path.
        sample_rate: Sample rate in Hz.
        channels: Number of channels (1 or 2).
        duration_sec: Total duration in seconds.
        silence_gaps: List of (start_sec, end_sec) silence gap ranges.
    """
    import numpy as np

    total_samples = int(sample_rate * duration_sec)
    # Fill with 0.5 amplitude tone (a simple sine wave)
    t = np.arange(total_samples, dtype=np.float32) / sample_rate
    audio = (np.sin(2 * np.pi * 440 * t) * 0.5).astype(np.float32)

    # Mute silence gaps
    for start_sec, end_sec in silence_gaps:
        start_sample = int(start_sec * sample_rate)
        end_sample = int(end_sec * sample_rate)
        audio[start_sample:end_sample] = 0.0

    if channels == 2:
        # Duplicate for stereo
        audio = np.column_stack((audio, audio))

    # Write WAV file manually to avoid soundfile dependency in tests
    _write_wav(path, audio, sample_rate, channels)


def _write_wav(path: Path, data: 'np.ndarray', sample_rate: int, channels: int):
    """Write numpy array as WAV file."""
    import numpy as np

    if data.ndim == 2:
        n_frames = data.shape[0]
        samples = data.flatten()
    else:
        n_frames = data.shape[0]
        samples = data

    # Convert float32 [-1, 1] to int16
    samples_i16 = (samples * 32767).astype(np.int16)

    byte_rate = sample_rate * channels * 2
    block_align = channels * 2
    data_size = len(samples_i16) * 2
    file_size = 36 + data_size

    with open(path, 'wb') as f:
        f.write(b'RIFF')
        f.write(struct.pack('<I', file_size))
        f.write(b'WAVE')
        f.write(b'fmt ')
        f.write(struct.pack('<I', 16))  # chunk size
        f.write(struct.pack('<H', 1))   # PCM
        f.write(struct.pack('<H', channels))
        f.write(struct.pack('<I', sample_rate))
        f.write(struct.pack('<I', byte_rate))
        f.write(struct.pack('<H', block_align))
        f.write(struct.pack('<H', 16))  # bits per sample
        f.write(b'data')
        f.write(struct.pack('<I', data_size))
        f.write(samples_i16.tobytes())


@pytest.fixture
def sample_wav_with_gaps(temp_dir):
    """Create a synthetic 3-track WAV file with clear silence gaps between tracks.

    Track layout:
        Track 1: 0:00 - 3:30 (210s)
        Gap 1:   3:30 - 3:32 (2s silence)
        Track 2: 3:32 - 7:15 (223s)
        Gap 2:   7:15 - 7:17 (2s silence)
        Track 3: 7:17 - 10:00 (163s)
    Total: 10:00 = 600s
    """
    path = temp_dir / "sample_3track.wav"
    _create_synthetic_wav(
        path,
        sample_rate=44100,
        channels=2,
        duration_sec=600.0,
        silence_gaps=[(210.0, 212.0), (435.0, 437.0)],
    )
    return path


@pytest.fixture
def sample_wav_gapless(temp_dir):
    """Create a synthetic gapless WAV file (no silence between tracks)."""
    path = temp_dir / "sample_gapless.wav"
    _create_synthetic_wav(
        path,
        sample_rate=44100,
        channels=2,
        duration_sec=300.0,
        silence_gaps=[],
    )
    return path


@pytest.fixture
def sample_wav_short(temp_dir):
    """Create a very short WAV file (2 seconds)."""
    path = temp_dir / "sample_short.wav"
    _create_synthetic_wav(
        path,
        sample_rate=44100,
        channels=2,
        duration_sec=2.0,
        silence_gaps=[],
    )
    return path
