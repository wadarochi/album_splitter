"""FLAC audio splitting backend.

Implements a fallback chain of lossless splitting tools:

1. ``flac-tracksplit`` - native frame-level FLAC splitter.
2. ``flacsplt`` - frame-level FLAC splitter from the mp3splt project.
3. ``shnsplit`` + ``flac.exe`` - sample-accurate decode/re-encode fallback.

If no backend is available, the module raises a clear error with installation hints.
"""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
from pathlib import Path
from typing import Protocol, cast

import numpy as np

from cue_finder.backends import wav_splitter


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


class _SoundFileModule(Protocol):
    SoundFile: type[_SoundFile]


_sf: _SoundFileModule | None = None


def _soundfile() -> _SoundFileModule:
    global _sf
    if _sf is None:
        _sf = cast(_SoundFileModule, cast(object, importlib.import_module("soundfile")))
    return _sf


def _find_backend() -> str | None:
    """Return the first available FLAC splitting backend name.

    Note: ``flac-tracksplit`` is intentionally deprioritized below
    ``shnsplit``. The upstream ``flac-tracksplit`` CLI (v0.1.0) expects FLAC
    files with an embedded CUE sheet and does not accept an external
    ``-c`` cue path, so it is not directly usable by cue-finder's
    generate-CUE-then-split workflow. Until the backend is updated to embed
    the CUE sheet into a temporary FLAC copy, prefer ``shnsplit`` (or
    ``flacsplt``) which handle external CUE files correctly.
    """
    if shutil.which("flacsplt"):
        return "flacsplt"
    if shutil.which("shnsplit") and (shutil.which("flac") or shutil.which("flac.exe")):
        return "shnsplit"
    if shutil.which("flac-tracksplit"):
        return "flac-tracksplit"
    return None


def _flac_to_wav(flac_path: str, wav_path: str) -> None:
    """Decode or convert a FLAC file to a WAV file using soundfile in streaming blocks."""
    with _soundfile().SoundFile(flac_path) as src, _soundfile().SoundFile(
        wav_path, "w", samplerate=src.samplerate, channels=src.channels, subtype="PCM_16", format="WAV"
    ) as dst:
        block_size = 65536
        while True:
            data = src.read(block_size)
            if len(data) == 0:
                break
            dst.write(data)


def _split_with_flac_tracksplit(
    flac_path: str,
    cue_path: str,
    output_dir: str,
) -> list[str]:
    """Use flac-tracksplit for frame-level lossless FLAC splitting."""
    cmd = [
        "flac-tracksplit",
        "-i", flac_path,
        "-o", output_dir,
        "-c", cue_path,
    ]
    _ = subprocess.run(cmd, check=True)
    return sorted(str(p) for p in Path(output_dir).glob("*.flac"))


def _split_with_flacsplt(
    flac_path: str,
    cue_path: str,
    output_dir: str,
) -> list[str]:
    """Use flacsplt for frame-level lossless FLAC splitting."""
    cmd = [
        "flacsplt",
        flac_path,
        "-c", cue_path,
        "-o", output_dir,
    ]
    _ = subprocess.run(cmd, check=True)
    return sorted(str(p) for p in Path(output_dir).glob("*.flac"))


def _split_with_shntool(
    flac_path: str,
    cue_path: str,
    output_dir: str,
) -> list[str]:
    """Use shnsplit with flac output as a last-resort sample-accurate fallback."""
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)
    cmd = [
        "shnsplit",
        "-f", cue_path,
        "-t", "%n - %t",
        "-o", "flac",
        flac_path,
    ]
    _ = subprocess.run(cmd, check=True, cwd=str(output_dir_path))
    return sorted(str(p) for p in output_dir_path.glob("*.flac"))


def split(
    flac_path: str,
    cue_path: str,
    output_dir: str,
    name_template: str = "{track:02d} - {title}.{format}",
    output_format: str = "flac",
    timestamps: list[float] | None = None,
    track_titles: list[str] | None = None,
    metadata: dict[str, str] | None = None,
) -> list[str]:
    """Split a FLAC file using the best available external backend.

    Args:
        flac_path: Path to the source FLAC file.
        cue_path: Path to the CUE sheet that drives splitting. If a backend
            requires a CUE file and ``cue_path`` is not provided, the caller
            must generate one first.
        output_dir: Directory where output files will be written.
        name_template: Python format string for output filenames.
        output_format: Target audio format (``"flac"`` or ``"wav"``). If the
            selected backend cannot directly produce WAV, tracks are converted
            via the WAV backend or soundfile.
        timestamps: Optional list of split points in seconds. Used when no
            CUE-level splitter is available and the caller decodes the FLAC to WAV.
        track_titles: Optional list of track titles for output naming.
        metadata: Optional dictionary of extra template variables.

    Returns:
        List of output file paths, one per track.

    Raises:
        RuntimeError: If no suitable FLAC splitting backend is available.
    """
    metadata = metadata or {}
    backend = _find_backend()

    if backend == "flac-tracksplit":
        paths = _split_with_flac_tracksplit(flac_path, cue_path, output_dir)
    elif backend == "flacsplt":
        paths = _split_with_flacsplt(flac_path, cue_path, output_dir)
    elif backend == "shnsplit":
        paths = _split_with_shntool(flac_path, cue_path, output_dir)
    elif timestamps is not None:
        import tempfile

        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmpdir:
            wav_path = os.path.join(tmpdir, "decoded.wav")
            _flac_to_wav(flac_path, wav_path)
            paths = wav_splitter.split_wav(
                wav_path=wav_path,
                timestamps=timestamps,
                output_dir=output_dir,
                name_template=name_template,
                output_format=output_format,
                track_titles=track_titles,
                metadata=metadata,
            )
    else:
        raise RuntimeError(
            "No FLAC splitting backend available. Install one of: flac-tracksplit, flacsplt, shnsplit (with flac helper), or provide a timestamp list."
        )

    if output_format.lower() == "wav" and paths and paths[0].lower().endswith(".flac"):
        converted: list[str] = []
        for flac_track in paths:
            wav_track = os.path.splitext(flac_track)[0] + ".wav"
            _flac_to_wav(flac_track, wav_track)
            converted.append(wav_track)
        return converted

    return paths
