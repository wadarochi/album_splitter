"""Audio splitting orchestrator.

The ``Splitter`` class auto-detects the input audio format, selects the
appropriate lossless backend, and splits the source file into tracks using
either a CUE sheet or a raw list of timestamps.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import ClassVar

from cue_finder.backends import ape_splitter, flac_splitter, wav_splitter


class Splitter:
    """Orchestrates format detection, backend selection, and track splitting."""

    BINARIES: ClassVar[tuple[str, ...]] = ("flac-tracksplit", "flacsplt", "shnsplit", "mac.exe", "ffmpeg")

    def __init__(self) -> None:
        """Initialize the splitter and detect available backends."""
        self.backends: dict[str, str | None] = {name: shutil.which(name) for name in self.BINARIES}

    @staticmethod
    def _detect_format(audio_path: str) -> str:
        """Return the audio format from the file extension (flac, wav, ape)."""
        ext = Path(audio_path).suffix.lower().lstrip(".")
        if ext in ("flac", "wav", "ape"):
            return ext
        raise ValueError(f"Unsupported audio format: {ext!r} ({audio_path})")

    @staticmethod
    def _time_to_seconds(value: str) -> float:
        """Convert a CUE INDEX 01 time (MM:SS:FF or seconds) to seconds."""
        value = value.strip()
        if re.match(r"^\d+(\.\d+)?$", value):
            return float(value)
        match = re.match(r"^(\d+):(\d+):(\d+)$", value)
        if match:
            minutes, seconds, frames = (int(g) for g in match.groups())
            return minutes * 60 + seconds + frames / 75.0
        raise ValueError(f"Invalid time value: {value!r}")

    @staticmethod
    def parse_cue(cue_path: str) -> tuple[list[float], list[str], dict[str, str]]:
        """Parse a CUE sheet for INDEX 01 split points and track titles.

        Returns:
            Tuple of (timestamps, track_titles, metadata). The first timestamp is
            always 0.0, and additional timestamps are derived from each track's
            INDEX 01 value.
        """
        cue_path = os.path.abspath(cue_path)
        cue_dir = os.path.dirname(cue_path)
        timestamps: list[float] = []
        track_titles: list[str] = []
        metadata: dict[str, str] = {}

        with open(cue_path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()

        current_title: str | None = None
        in_track = False
        for line in lines:
            line = line.strip()
            if not line:
                continue
            upper = line.upper()
            if upper.startswith("PERFORMER "):
                metadata["artist"] = line.split(" ", 1)[1].strip().strip('"')
            elif upper.startswith("TITLE ") and not in_track:
                metadata["album"] = line.split(" ", 1)[1].strip().strip('"')
            elif upper.startswith("FILE "):
                parts = line.split(" ", 2)
                if len(parts) >= 2:
                    referenced = parts[1].strip().strip('"')
                    metadata["referenced_audio"] = os.path.join(cue_dir, referenced)
            elif upper.startswith("TRACK "):
                in_track = True
                if current_title is not None:
                    track_titles.append(current_title)
                current_title = None
            elif upper.startswith("TITLE ") and in_track:
                current_title = line.split(" ", 1)[1].strip().strip('"')
            elif upper.startswith("INDEX 01 "):
                time_str = line.split(" ", 2)[2].strip()
                timestamps.append(Splitter._time_to_seconds(time_str))

        if current_title is not None:
            track_titles.append(current_title)

        timestamps = sorted(set([0.0] + timestamps))

        return timestamps, track_titles, metadata

    def report_backends(self) -> dict[str, object]:
        """Return a dictionary showing which backends are available.

        The returned dictionary contains each binary name mapped to a boolean
        indicating whether it was found in PATH, plus a ``selected`` key describing
        which backend will be used for each supported format.
        """
        selected: dict[str, str | None] = {
            "flac": None,
            "wav": "wave",
            "ape": None,
        }
        if self.backends.get("flac-tracksplit"):
            selected["flac"] = "flac-tracksplit"
        elif self.backends.get("flacsplt"):
            selected["flac"] = "flacsplt"
        elif self.backends.get("shnsplit"):
            selected["flac"] = "shnsplit"

        if self.backends.get("mac.exe") or self.backends.get("mac"):
            selected["ape"] = "mac.exe"

        return {
            "binaries": self.backends,
            "selected": selected,
        }

    def split(
        self,
        audio_path: str,
        cue_path_or_timestamps: str | list[float] | None = None,
        output_dir: str | None = None,
        format: str | None = None,
        name_template: str | None = None,
    ) -> list[str]:
        """Split an audio file into tracks.

        Args:
            audio_path: Path to the source audio file (FLAC, WAV, or APE).
            cue_path_or_timestamps: Either a CUE sheet path or a list of split
                points in seconds. If omitted, the file is treated as a single track.
            output_dir: Directory for output files. Defaults to a sibling directory
                named after the input file with ``_tracks`` appended.
            format: Output audio format (``"flac"`` or ``"wav"``). Defaults to the
                input format.
            name_template: Python format string for output filenames. Defaults
                to ``"{track:02d} - {title}.{format}"``.

        Returns:
            List of output file paths, one per track.

        Raises:
            RuntimeError: If no suitable backend is available for the input format.
        """
        audio_path = os.path.abspath(audio_path)
        input_format = self._detect_format(audio_path)
        output_format = (format or input_format).lower()
        if output_format not in ("flac", "wav"):
            raise ValueError(f"Unsupported output format: {output_format!r}")

        if output_dir is None:
            base = Path(audio_path).stem
            output_dir = str(Path(audio_path).parent / f"{base}_tracks")
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        template = name_template or "{track:02d} - {title}.{format}"

        timestamps: list[float] = [0.0]
        track_titles: list[str] = []
        metadata: dict[str, str] = {}

        if cue_path_or_timestamps is None:
            track_titles = [Path(audio_path).stem]
        elif isinstance(cue_path_or_timestamps, str):
            timestamps, track_titles, metadata = self.parse_cue(cue_path_or_timestamps)
        else:
            timestamps = sorted([0.0] + [float(t) for t in cue_path_or_timestamps if float(t) > 0.0])
            track_titles = [f"Track {i + 1}" for i in range(len(timestamps) - 1)]

        if input_format == "flac":
            cue_path = cue_path_or_timestamps if isinstance(cue_path_or_timestamps, str) else ""
            return flac_splitter.split(
                flac_path=audio_path,
                cue_path=cue_path,
                output_dir=output_dir,
                name_template=template,
                output_format=output_format,
                timestamps=timestamps,
                track_titles=track_titles,
                metadata=metadata,
            )

        if input_format == "wav":
            return wav_splitter.split_wav(
                wav_path=audio_path,
                timestamps=timestamps,
                output_dir=output_dir,
                name_template=template,
                output_format=output_format,
                track_titles=track_titles,
                metadata=metadata,
            )

        if input_format == "ape":
            return ape_splitter.split(
                ape_path=audio_path,
                timestamps=timestamps,
                output_dir=output_dir,
                name_template=template,
                output_format=output_format,
                track_titles=track_titles,
                metadata=metadata,
            )

        raise RuntimeError(f"No backend available for format: {input_format}")
