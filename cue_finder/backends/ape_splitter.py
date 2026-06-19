"""APE (Monkey's Audio) splitting backend.

APE files cannot be split at the frame level, so the strategy is:

1. Decode the APE file to a temporary WAV using ``mac.exe``.
2. Split the WAV using the WAV backend.
3. If the requested output format is FLAC, re-encode each track using soundfile.
4. Clean up the temporary WAV file.
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


def _decode_ape_to_wav(ape_path: str, wav_path: str) -> None:
    """Decode an APE file to a WAV file using ffmpeg (primary) or mac.exe (fallback)."""
    ffmpeg_bin = shutil.which("ffmpeg")
    if ffmpeg_bin:
        cmd = [ffmpeg_bin, "-i", ape_path, "-c:a", "pcm_s16le", "-y", wav_path]
        _ = subprocess.run(cmd, check=True, capture_output=True)
        return

    mac_binary = shutil.which("mac.exe") or shutil.which("mac")
    if mac_binary:
        cmd = [mac_binary, ape_path, wav_path, "-d"]
        _ = subprocess.run(cmd, check=True)
        return

    raise RuntimeError(
        "No APE decoder found. Install ffmpeg or Monkey's Audio 'mac.exe' / 'mac' and ensure it is in PATH."
    )


def _encode_wav_to_flac(wav_path: str, flac_path: str) -> None:
    """Re-encode a WAV file to FLAC using soundfile in streaming blocks."""
    with _soundfile().SoundFile(wav_path) as src, _soundfile().SoundFile(
        flac_path, "w", samplerate=src.samplerate, channels=src.channels, subtype="PCM_16", format="FLAC"
    ) as dst:
        block_size = 65536
        while True:
            data = src.read(block_size)
            if len(data) == 0:
                break
            dst.write(data)


def split(
    ape_path: str,
    timestamps: list[float],
    output_dir: str,
    name_template: str = "{track:02d} - {title}.{format}",
    output_format: str = "flac",
    track_titles: list[str] | None = None,
    metadata: dict[str, str] | None = None,
) -> list[str]:
    """Split an APE file by decoding to WAV, splitting, and optionally re-encoding.

    Args:
        ape_path: Path to the source APE file.
        timestamps: List of split points in seconds. The first track starts at 0.0
            and the last track ends at the end of the file.
        output_dir: Directory where output files will be written.
        name_template: Python format string for output filenames.
        output_format: Target audio format (``"flac"`` or ``"wav"``). FLAC is the
            natural output format for APE sources.
        track_titles: Optional list of track titles for output naming.
        metadata: Optional dictionary of extra template variables.

    Returns:
        List of output file paths, one per track.

    Raises:
        RuntimeError: If ``mac.exe`` / ``mac`` is not available in PATH.
    """
    metadata = metadata or {}

    if not shutil.which("ffmpeg") and not shutil.which("mac.exe") and not shutil.which("mac"):
        raise RuntimeError(
            "No APE decoder available. Install ffmpeg or Monkey's Audio 'mac.exe' (Windows) / 'mac' (Linux/macOS) and add it to PATH."
        )

    import tempfile

    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_wav = os.path.join(tmpdir, "decoded_ape.wav")
        _decode_ape_to_wav(ape_path, tmp_wav)

        wav_paths = wav_splitter.split_wav(
            wav_path=tmp_wav,
            timestamps=list(timestamps),
            output_dir=output_dir,
            name_template=name_template,
            output_format="wav",
            track_titles=track_titles,
            metadata=metadata,
        )

        if output_format.lower() == "flac":
            flac_paths: list[str] = []
            for wav_track in wav_paths:
                flac_track = os.path.splitext(wav_track)[0] + ".flac"
                _encode_wav_to_flac(wav_track, flac_track)
                os.remove(wav_track)
                flac_paths.append(flac_track)
            return flac_paths

        return wav_paths
