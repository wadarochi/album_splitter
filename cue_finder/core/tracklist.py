from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

import yaml


@dataclass
class AlbumMeta:
    artist: str = ""
    title: str = ""
    date: str = ""
    source: str = ""
    source_id: str = ""


@dataclass
class TrackEntry:
    title: str = ""
    artist: str | None = None
    duration: float | None = None
    start: float | None = None
    end: float | None = None
    confidence: float | None = None


@dataclass
class PerDiscTracklist:
    file: str = ""
    tracks: list[TrackEntry] = field(default_factory=list)
    detected_boundaries: list[float] = field(default_factory=list)


@dataclass
class Tracklist:
    album: AlbumMeta = field(default_factory=AlbumMeta)
    tracks: list[TrackEntry] = field(default_factory=list)
    detected_boundaries: list[float] = field(default_factory=list)
    cue_file: str | None = None
    output_dir: str | None = None
    discs: list[PerDiscTracklist] = field(default_factory=list)


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value == "":
        return True
    if isinstance(value, list) and not value:
        return True
    if isinstance(value, dict) and not value:
        return True
    return False


def _tracklist_to_dict(obj: Any) -> Any:
    if isinstance(obj, (Tracklist, PerDiscTracklist, AlbumMeta, TrackEntry)):
        result: dict[str, Any] = {}
        for field_name in obj.__dataclass_fields__:
            value = getattr(obj, field_name)
            converted = _tracklist_to_dict(value)
            if not _is_empty(converted):
                result[field_name] = converted
        return result
    if isinstance(obj, list):
        return [_tracklist_to_dict(item) for item in obj]
    if _is_numpy(obj):
        return float(obj)
    return obj


def _is_numpy(obj: Any) -> bool:
    try:
        import numpy as np
        return isinstance(obj, (np.floating, np.integer))
    except ImportError:
        return False


def _dict_to_track_entry(data: dict[str, Any]) -> TrackEntry:
    return TrackEntry(
        title=data.get("title", ""),
        artist=data.get("artist"),
        duration=data.get("duration"),
        start=data.get("start"),
        end=data.get("end"),
        confidence=data.get("confidence"),
    )


def _dict_to_album_meta(data: dict[str, Any]) -> AlbumMeta:
    return AlbumMeta(
        artist=data.get("artist", ""),
        title=data.get("title", ""),
        date=data.get("date", ""),
        source=data.get("source", ""),
        source_id=data.get("source_id", ""),
    )


def _dict_to_per_disc(data: dict[str, Any]) -> PerDiscTracklist:
    return PerDiscTracklist(
        file=data.get("file", ""),
        tracks=[_dict_to_track_entry(t) for t in data.get("tracks", [])],
        detected_boundaries=list(data.get("detected_boundaries", [])),
    )


def _dict_to_tracklist(data: dict[str, Any]) -> Tracklist:
    return Tracklist(
        album=_dict_to_album_meta(data.get("album", {})),
        tracks=[_dict_to_track_entry(t) for t in data.get("tracks", [])],
        detected_boundaries=list(data.get("detected_boundaries", [])),
        cue_file=data.get("cue_file"),
        output_dir=data.get("output_dir"),
        discs=[_dict_to_per_disc(d) for d in data.get("discs", [])],
    )


def save_tracklist(tracklist: Tracklist, path: str) -> None:
    data = _tracklist_to_dict(tracklist)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def load_tracklist(path: str) -> Tracklist:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        data = {}
    return _dict_to_tracklist(data)


def parse_plain_text(text: str) -> Tracklist:
    tracks: list[TrackEntry] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if " - " in line:
            artist, title = line.split(" - ", 1)
            tracks.append(TrackEntry(title=title.strip(), artist=artist.strip()))
        else:
            tracks.append(TrackEntry(title=line, artist=""))
    return Tracklist(tracks=tracks)


def detect_format(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in (".yaml", ".yml"):
        return "yaml"
    if ext == ".txt":
        return "text"

    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except (FileNotFoundError, OSError):
        return "yaml"
    if content.lstrip().startswith("album:"):
        return "yaml"
    return "text"


def validate_tracklist(tracklist: Tracklist) -> list[str]:
    errors: list[str] = []
    all_tracks: list[TrackEntry] = []
    all_tracks.extend(tracklist.tracks)
    for disc in tracklist.discs:
        all_tracks.extend(disc.tracks)

    if not all_tracks:
        errors.append("At least one track is required")
        return errors

    for i, track in enumerate(all_tracks, start=1):
        if not track.title or not track.title.strip():
            errors.append(f"Track {i} has an empty title")
        if track.duration is not None and track.duration <= 0:
            errors.append(f"Track {i} has a non-positive duration")

    def _check_boundaries(boundaries: list[float], label: str = "") -> None:
        for i in range(1, len(boundaries)):
            if boundaries[i] < boundaries[i - 1]:
                prefix = f"{label} " if label else ""
                errors.append(
                    f"{prefix}Boundary {i} ({boundaries[i]}) is less than boundary {i - 1} ({boundaries[i - 1]}); boundaries must be non-decreasing"
                )

    _check_boundaries(tracklist.detected_boundaries)
    for disc_idx, disc in enumerate(tracklist.discs, start=1):
        _check_boundaries(disc.detected_boundaries, f"Disc {disc_idx}")

    return errors


def export_tracklist(tracklist: Tracklist, format: str) -> str:
    fmt = format.lower()
    if fmt == "yaml":
        return yaml.safe_dump(_tracklist_to_dict(tracklist), allow_unicode=True, sort_keys=False)
    if fmt == "json":
        return json.dumps(_tracklist_to_dict(tracklist), ensure_ascii=False, indent=2)
    if fmt == "text":
        lines: list[str] = []
        for track in tracklist.tracks:
            if track.artist:
                lines.append(f"{track.artist} - {track.title}")
            else:
                lines.append(track.title)
        return "\n".join(lines)
    if fmt == "cue":
        import importlib

        try:
            cue_module = importlib.import_module("cue_finder.core.cue")
            return cue_module.generate_cue(tracklist)
        except Exception as e:
            raise RuntimeError(f"Failed to export tracklist to CUE: {e}") from e
    raise ValueError(f"Unsupported export format: {format}")


__all__ = [
    "AlbumMeta",
    "TrackEntry",
    "PerDiscTracklist",
    "Tracklist",
    "save_tracklist",
    "load_tracklist",
    "parse_plain_text",
    "detect_format",
    "validate_tracklist",
    "export_tracklist",
]
