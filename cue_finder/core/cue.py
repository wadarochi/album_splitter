"""CUE sheet generation and parsing module."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict

FRAMES_PER_SECOND = 75

__all__ = [
    "CueSheet",
    "CueTrack",
    "generate_cue",
    "generate_cue_multidisc",
    "msf_to_seconds",
    "parse_cue",
    "samples_to_msf",
    "seconds_to_msf",
    "validate_cue",
    "write_cue",
]


class _TrackDict(TypedDict, total=False):
    track_number: int
    title: str
    performer: str
    start_seconds: float
    index01: str


class _DiscDict(TypedDict, total=False):
    audio_filename: str
    tracks: list[_TrackDict]
    album_artist: str
    album_title: str
    rem_fields: dict[str, str]


class _ParsedTrackDict(TypedDict):
    track_number: int
    title: str
    performer: str
    index01: str
    start_seconds: float


class _ValidationTrackDict(TypedDict):
    track_number: int
    index01: str | None


def samples_to_msf(samples: int, sample_rate: int) -> str:
    """Convert a sample position to CUE MSF format (MM:SS:FF).

    Frames are computed at 75 frames per second. The frame count is rounded to
    the nearest whole frame.
    """
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    frames_per_sample = sample_rate / FRAMES_PER_SECOND
    total_frames = round(samples / frames_per_sample)
    frames = total_frames % FRAMES_PER_SECOND
    total_seconds = total_frames // FRAMES_PER_SECOND
    seconds = total_seconds % 60
    minutes = total_seconds // 60
    return f"{minutes:02d}:{seconds:02d}:{frames:02d}"


def seconds_to_msf(seconds: float, sample_rate: int) -> str:
    """Convert floating-point seconds to CUE MSF format via sample count."""
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    samples = round(seconds * sample_rate)
    return samples_to_msf(samples, sample_rate)


def msf_to_seconds(msf: str) -> float:
    """Parse a CUE MSF timestamp (MM:SS:FF or MM:SS) into seconds."""
    msf = msf.strip()
    parts = msf.split(":")
    if len(parts) == 2:
        minutes_str, seconds_str = parts
        frames_str = "0"
    elif len(parts) == 3:
        minutes_str, seconds_str, frames_str = parts
    else:
        raise ValueError(f"Invalid MSF format: {msf!r}")
    minutes = int(minutes_str)
    seconds = int(seconds_str)
    frames = int(frames_str)
    return minutes * 60 + seconds + frames / FRAMES_PER_SECOND


@dataclass
class CueTrack:
    """A single track within a CUE sheet."""

    track_number: int
    title: str = ""
    performer: str = ""
    index01: str = "00:00:00"
    start_seconds: float = 0.0


@dataclass
class CueSheet:
    """A parsed or generated CUE sheet."""

    performer: str = ""
    title: str = ""
    audio_filename: str = ""
    tracks: list[CueTrack] = field(default_factory=list)
    rem_fields: dict[str, str] = field(default_factory=dict)

    def to_text(self) -> str:
        """Regenerate the CUE sheet text for this sheet."""
        return generate_cue(
            album_artist=self.performer,
            album_title=self.title,
            audio_filename=self.audio_filename,
            matched_tracks=self.tracks,
            rem_fields=self.rem_fields,
        )


def _quote_cue(value: str) -> str:
    """Return a string safe to embed inside CUE double quotes."""
    return value.replace('"', "'")


def _unquote_cue(value: str) -> str:
    """Strip surrounding double quotes from a CUE field value."""
    value = value.strip()
    if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    return value


def _track_from_item(
    item: CueTrack | _TrackDict,
    default_number: int = 1,
    sample_rate: int = 44100,
) -> CueTrack:
    """Normalize a CueTrack or dict into a CueTrack instance."""
    if isinstance(item, CueTrack):
        return item
    track_number = item.get("track_number", default_number)
    title = item.get("title", "")
    performer = item.get("performer", "")
    start_seconds = item.get("start_seconds", None)
    index01 = item.get("index01", "")
    if not index01 and start_seconds is not None:
        index01 = seconds_to_msf(start_seconds, sample_rate)
    if start_seconds is None and index01:
        start_seconds = msf_to_seconds(index01)
    if start_seconds is None:
        start_seconds = 0.0
    return CueTrack(
        track_number=track_number,
        title=title,
        performer=performer,
        index01=index01 if index01 else "00:00:00",
        start_seconds=start_seconds,
    )


def generate_cue(
    album_artist: str,
    album_title: str,
    audio_filename: str,
    matched_tracks: Iterable[CueTrack | _TrackDict],
    rem_fields: dict[str, str] | None = None,
) -> str:
    """Generate a standard CUE sheet as a single string."""
    if rem_fields is None:
        rem_fields = {}
    tracks = [_track_from_item(item, i + 1) for i, item in enumerate(matched_tracks)]
    audio_basename = Path(audio_filename).name

    lines: list[str] = []
    if album_artist:
        lines.append(f'PERFORMER "{_quote_cue(album_artist)}"')
    if album_title:
        lines.append(f'TITLE "{_quote_cue(album_title)}"')
    for key in ("DATE", "GENRE", "DISCID", "COMMENT"):
        if key in rem_fields:
            lines.append(f'REM {key} "{_quote_cue(rem_fields[key])}"')
    lines.append(f'FILE "{_quote_cue(audio_basename)}" WAVE')

    for track in tracks:
        track_num_str = f"{track.track_number:02d}"
        lines.append(f"  TRACK {track_num_str} AUDIO")
        if track.title:
            lines.append(f'    TITLE "{_quote_cue(track.title)}"')
        if track.performer and track.performer != album_artist:
            lines.append(f'    PERFORMER "{_quote_cue(track.performer)}"')
        lines.append(f"    INDEX 01 {track.index01}")

    return "\n".join(lines)


def write_cue(cue_text: str, output_path: str | Path) -> None:
    """Write a CUE sheet to disk using UTF-8 with BOM for Windows tools."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _ = output_path.write_text(cue_text, encoding="utf-8-sig")


def parse_cue(cue_path: str | Path) -> CueSheet:
    """Parse an existing CUE file and return a CueSheet object."""
    cue_path = Path(cue_path)
    text = cue_path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()

    performer = ""
    title = ""
    audio_filename = ""
    rem_fields: dict[str, str] = {}
    tracks: list[_ParsedTrackDict] = []
    current_track: _ParsedTrackDict | None = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith(";"):
            continue

        if line.startswith("REM "):
            rest = line[4:].strip()
            parts = rest.split(None, 1)
            if parts:
                key = parts[0]
                value = _unquote_cue(parts[1]) if len(parts) > 1 else ""
                rem_fields[key] = value
        elif line.startswith("PERFORMER "):
            value = _unquote_cue(line[10:].strip())
            if current_track is not None:
                current_track["performer"] = value
            else:
                performer = value
        elif line.startswith("TITLE "):
            value = _unquote_cue(line[6:].strip())
            if current_track is not None:
                current_track["title"] = value
            else:
                title = value
        elif line.startswith("FILE "):
            rest = line[5:].strip()
            match = re.match(r'^"([^"]*)"(?:\s+(.+))?$', rest)
            if match:
                audio_filename = match.group(1)
            else:
                parts = rest.split(None, 1)
                audio_filename = parts[0]
            current_track = None
        elif line.startswith("TRACK "):
            rest = line[6:].strip()
            parts = rest.split()
            if not parts:
                continue
            track_number = int(parts[0])
            current_track = {
                "track_number": track_number,
                "title": "",
                "performer": "",
                "index01": "",
                "start_seconds": 0.0,
            }
            tracks.append(current_track)
        elif line.startswith("INDEX "):
            rest = line[6:].strip()
            parts = rest.split(None, 1)
            if len(parts) >= 2 and parts[0] == "01" and current_track is not None:
                index01 = parts[1]
                current_track["index01"] = index01
                current_track["start_seconds"] = msf_to_seconds(index01)

    cue_tracks = [
        CueTrack(
            track_number=t["track_number"],
            title=t["title"],
            performer=t["performer"],
            index01=t["index01"] if t["index01"] else "00:00:00",
            start_seconds=t["start_seconds"],
        )
        for t in tracks
    ]

    return CueSheet(
        performer=performer,
        title=title,
        audio_filename=audio_filename,
        tracks=cue_tracks,
        rem_fields=rem_fields,
    )


def validate_cue(cue_text: str) -> list[str]:
    """Validate a CUE sheet and return a list of error strings."""
    errors: list[str] = []
    lines = cue_text.splitlines()

    parsed_tracks: list[_ValidationTrackDict] = []
    current_track: _ValidationTrackDict | None = None
    has_file = False

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith(";"):
            continue

        if line.startswith("FILE "):
            has_file = True
            current_track = None
        elif line.startswith("TRACK "):
            rest = line[6:].strip()
            parts = rest.split()
            if not parts:
                continue
            current_track = {
                "track_number": int(parts[0]),
                "index01": None,
            }
            parsed_tracks.append(current_track)
        elif line.startswith("INDEX "):
            rest = line[6:].strip()
            parts = rest.split(None, 1)
            if len(parts) >= 2 and parts[0] == "01" and current_track is not None:
                current_track["index01"] = parts[1]

    if not has_file:
        errors.append("Missing FILE entry")

    if not parsed_tracks:
        errors.append("No tracks found")
        return errors

    expected = 1
    for track in parsed_tracks:
        if track["track_number"] != expected:
            errors.append("Track numbers must be sequential")
            break
        expected += 1

    for i, track in enumerate(parsed_tracks):
        if track["index01"] is None:
            errors.append(f"Track {track['track_number']:02d} missing required INDEX 01")
            continue

        try:
            seconds = msf_to_seconds(track["index01"])
        except ValueError:
            errors.append(
                f"Track {track['track_number']:02d} has invalid INDEX 01: {track['index01']}"
            )
            continue

        if i == 0 and seconds != 0.0:
            errors.append("First track must start at 00:00:00")

        if i > 0:
            previous_index01 = parsed_tracks[i - 1]["index01"]
            if previous_index01 is not None:
                previous_seconds = msf_to_seconds(previous_index01)
                if seconds < previous_seconds:
                    errors.append(
                        f"Track {track['track_number']:02d} timestamp is before previous track"
                    )

    return errors


def generate_cue_multidisc(discs: Iterable[CueSheet | _DiscDict]) -> str:
    """Generate a CUE sheet for a multi-disc album.

    Each disc is expected to be a dict or CueSheet with keys/fields:
    audio_filename, tracks, and optionally album_artist, album_title, rem_fields.
    Track numbers continue sequentially across discs.
    """
    lines: list[str] = []
    first_disc = True
    global_track_number = 1
    album_artist = ""
    album_title = ""

    for disc in discs:
        if isinstance(disc, CueSheet):
            audio_filename = disc.audio_filename
            disc_tracks = disc.tracks
            disc_artist = disc.performer
            disc_title = disc.title
            rem_fields = disc.rem_fields
        else:
            audio_filename = disc.get("audio_filename", "")
            disc_tracks = disc.get("tracks", [])
            disc_artist = disc.get("album_artist", "")
            disc_title = disc.get("album_title", "")
            rem_fields = disc.get("rem_fields", {})

        audio_basename = Path(audio_filename).name

        if first_disc:
            album_artist = disc_artist
            album_title = disc_title
            if album_artist:
                lines.append(f'PERFORMER "{_quote_cue(album_artist)}"')
            if album_title:
                lines.append(f'TITLE "{_quote_cue(album_title)}"')
            for key in ("DATE", "GENRE", "DISCID", "COMMENT"):
                if key in rem_fields:
                    lines.append(f'REM {key} "{_quote_cue(rem_fields[key])}"')
            first_disc = False

        lines.append(f'FILE "{_quote_cue(audio_basename)}" WAVE')

        for item in disc_tracks:
            track = _track_from_item(item, global_track_number)
            track_num_str = f"{global_track_number:02d}"
            lines.append(f"  TRACK {track_num_str} AUDIO")
            if track.title:
                lines.append(f'    TITLE "{_quote_cue(track.title)}"')
            if track.performer and track.performer != album_artist:
                lines.append(f'    PERFORMER "{_quote_cue(track.performer)}"')
            lines.append(f"    INDEX 01 {track.index01}")
            global_track_number += 1

    return "\n".join(lines)
