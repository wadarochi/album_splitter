"""WAV audio splitting backend using Python's built-in wave module.

Supports sample-accurate splitting of mono/stereo WAV files with streaming
block-based reads and writes. Can also produce FLAC output via soundfile.
"""

from __future__ import annotations

import importlib
import wave
from pathlib import Path
from typing import Protocol, cast

import numpy as np


class _SoundFile(Protocol):
    channels: int
    samplerate: int
    frames: int
    subtype: str

    def __init__(
        self,
        file: str,
        mode: str = "r",
        samplerate: int | None = None,
        channels: int | None = None,
        subtype: str | None = None,
        format: str | None = None,
    ) -> None: ...
    def __enter__(self) -> _SoundFile: ...
    def __exit__(self, *exc: object) -> None: ...
    def read(self, frames: int) -> np.ndarray: ...
    def write(self, data: np.ndarray) -> None: ...
    def seek(self, frames: int) -> None: ...


class _SoundFileModule(Protocol):
    SoundFile: type[_SoundFile]


_sf: _SoundFileModule | None = None


def _soundfile() -> _SoundFileModule:
    global _sf
    if _sf is None:
        _sf = cast(_SoundFileModule, cast(object, importlib.import_module("soundfile")))
    return _sf


def _format_filename(name_template: str, format: str, track_number: int, title: str, metadata: dict[str, str]) -> str:
    ctx = {
        "track": track_number,
        "title": title,
        "format": format,
    }
    ctx.update({k: str(v) for k, v in metadata.items() if k not in ctx})
    name = name_template.format(**ctx)
    if not name.lower().endswith(f".{format}"):
        name = f"{name}.{format}"
    return name


def _seconds_to_frame_index(seconds: float, framerate: int, nframes: int) -> int:
    idx = int(seconds * framerate)
    if idx < 0:
        idx = 0
    if idx > nframes:
        idx = nframes
    return idx


def _split_wav_to_wav(
    wav_path: str,
    timestamps: list[float],
    output_dir: str,
    name_template: str,
    track_titles: list[str] | None,
    metadata: dict[str, str],
) -> list[str]:
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)

    with wave.open(wav_path, "rb") as src:
        nchannels = src.getnchannels()
        sampwidth = src.getsampwidth()
        framerate = src.getframerate()
        nframes = src.getnframes()
        frame_size = nchannels * sampwidth

        timestamps = sorted(timestamps)
        if not timestamps or timestamps[0] != 0.0:
            timestamps = [0.0] + timestamps
        if timestamps[-1] < nframes / framerate:
            timestamps = timestamps + [nframes / framerate]

        track_titles = track_titles or []
        output_paths: list[str] = []
        block_size = 65536

        for i in range(len(timestamps) - 1):
            start_sec = timestamps[i]
            end_sec = timestamps[i + 1]
            start_frame = _seconds_to_frame_index(start_sec, framerate, nframes)
            end_frame = _seconds_to_frame_index(end_sec, framerate, nframes)
            if end_frame <= start_frame:
                continue

            title = track_titles[i] if i < len(track_titles) else f"Track {i + 1}"
            filename = _format_filename(name_template, "wav", i + 1, title, metadata)
            out_path = output_dir_path / filename
            output_paths.append(str(out_path))

            src.setpos(start_frame)
            remaining = end_frame - start_frame
            with wave.open(str(out_path), "wb") as dst:
                dst.setnchannels(nchannels)
                dst.setsampwidth(sampwidth)
                dst.setframerate(framerate)
                while remaining > 0:
                    to_read = min(block_size, remaining)
                    data = src.readframes(to_read)
                    if not data:
                        break
                    dst.writeframes(data)
                    remaining -= len(data) // frame_size

    return output_paths


def _split_wav_to_flac(
    wav_path: str,
    timestamps: list[float],
    output_dir: str,
    name_template: str,
    track_titles: list[str] | None,
    metadata: dict[str, str],
) -> list[str]:
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)

    with _soundfile().SoundFile(wav_path) as src:
        nchannels = src.channels
        samplerate = src.samplerate
        nframes = src.frames
        subtype = src.subtype

        timestamps = sorted(timestamps)
        if not timestamps or timestamps[0] != 0.0:
            timestamps = [0.0] + timestamps
        if timestamps[-1] < nframes / samplerate:
            timestamps = timestamps + [nframes / samplerate]

        track_titles = track_titles or []
        output_paths: list[str] = []
        block_size = 65536

        for i in range(len(timestamps) - 1):
            start_sec = timestamps[i]
            end_sec = timestamps[i + 1]
            start_frame = _seconds_to_frame_index(start_sec, samplerate, nframes)
            end_frame = _seconds_to_frame_index(end_sec, samplerate, nframes)
            if end_frame <= start_frame:
                continue

            title = track_titles[i] if i < len(track_titles) else f"Track {i + 1}"
            filename = _format_filename(name_template, "flac", i + 1, title, metadata)
            out_path = output_dir_path / filename
            output_paths.append(str(out_path))

            src.seek(start_frame)
            remaining = end_frame - start_frame
            with _soundfile().SoundFile(str(out_path), "w", samplerate=samplerate, channels=nchannels, subtype=subtype, format="FLAC") as dst:
                while remaining > 0:
                    to_read = min(block_size, remaining)
                    data = src.read(to_read)
                    if len(data) == 0:
                        break
                    dst.write(data)
                    remaining -= len(data)

    return output_paths


def split_wav(
    wav_path: str,
    timestamps: list[float],
    output_dir: str,
    name_template: str = "{track:02d} - {title}.{format}",
    output_format: str = "wav",
    track_titles: list[str] | None = None,
    metadata: dict[str, str] | None = None,
) -> list[str]:
    metadata = metadata or {}
    if output_format.lower() == "flac":
        return _split_wav_to_flac(wav_path, timestamps, output_dir, name_template, track_titles, metadata)
    return _split_wav_to_wav(wav_path, timestamps, output_dir, name_template, track_titles, metadata)
