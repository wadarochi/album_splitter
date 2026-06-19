"""Tagging module for cue-finder: cuetag and beets integration."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, cast, runtime_checkable

import yaml
from mutagen._file import File as MutagenFile
from mutagen.flac import FLAC
from mutagen.id3._frames import TALB, TIT2, TPE1, TRCK
from mutagen.mp3 import MP3


REQUIRED_BEETS_PLUGINS = ("chroma", "musicbrainz", "discogs", "fromfilename")
SUPPORTED_AUDIO_EXTS = (".flac", ".mp3", ".ape", ".wav", ".ogg", ".oga", ".m4a")
REQUIRED_TAG_FIELDS = {
    "title": ("title", "TITLE", "TIT2"),
    "artist": ("artist", "ARTIST", "TPE1"),
    "album": ("album", "ALBUM", "TALB"),
    "tracknumber": ("tracknumber", "TRACKNUMBER", "TRCK"),
}


__all__ = ["TagResult", "check_beets_installed", "tag_tracks"]


@dataclass
class TagResult:
    """Result of a tagging operation."""

    success: bool = False
    tagged_files: list[str] = field(default_factory=list)
    missing_tags: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class TrackInfo:
    """Track metadata extracted from a CUE sheet."""

    number: int
    title: str
    artist: str


@dataclass
class CueData:
    """Album and track metadata extracted from a CUE sheet."""

    album_title: str
    album_artist: str
    tracks: list[TrackInfo]


@runtime_checkable
class TagContainer(Protocol):
    """Protocol for a read-only tag container returned by mutagen."""

    def __getitem__(self, key: str) -> object: ...

    def get(self, key: str, default: object | None = None) -> object | None: ...


def check_beets_installed() -> bool:
    """Return True if the ``beet`` CLI is available in PATH."""
    return shutil.which("beet") is not None


def _check_cuetag_installed() -> bool:
    """Return True if the ``cuetag`` CLI is available in PATH."""
    return shutil.which("cuetag") is not None


def _default_beets_config_path() -> Path | None:
    """Return the default beets configuration path for the current platform."""
    home = Path.home()
    candidates: list[Path] = []
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidates.append(Path(appdata) / "beets" / "config.yaml")
        else:
            candidates.append(home / "AppData" / "Roaming" / "beets" / "config.yaml")
    elif os.name == "darwin":
        candidates.append(
            home / "Library" / "Application Support" / "beets" / "config.yaml"
        )
    else:
        candidates.append(home / ".config" / "beets" / "config.yaml")

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0] if candidates else None


def _beets_config_path(beets_config: str | None) -> Path | None:
    """Resolve the beets configuration path."""
    if beets_config:
        path = Path(beets_config).expanduser()
        if path.exists():
            return path
        return None
    return _default_beets_config_path()


def _verify_beets_plugins(config_path: Path | None) -> list[str]:
    """Check beets config for required plugins and return warnings for missing ones."""
    warnings: list[str] = []
    if config_path is None:
        warnings.append("Beets config not found; plugin verification skipped.")
        return warnings

    try:
        with config_path.open("r", encoding="utf-8") as handle:
            config: object = yaml.safe_load(handle) or {}
    except Exception as exc:
        warnings.append(f"Failed to parse beets config {config_path}: {exc}")
        return warnings

    if not isinstance(config, dict):
        warnings.append(
            f"Unexpected beets config type: {type(config).__name__}"
        )
        return warnings

    config_map: dict[str, object] = {}
    for key, value in config.items():
        config_map[str(key)] = value

    plugins: object = config_map.get("plugins", [])
    if isinstance(plugins, str):
        plugin_set = set(plugins.split())
    elif isinstance(plugins, list):
        plugin_set = {str(p).lower() for p in plugins}
    else:
        warnings.append(
            f"Unexpected 'plugins' type in beets config: {type(plugins).__name__}"
        )
        return warnings

    for required in REQUIRED_BEETS_PLUGINS:
        if required.lower() not in plugin_set:
            warnings.append(f"Beets config missing recommended plugin: {required}")

    return warnings


def _extract_quoted(line: str) -> str:
    """Extract the first quoted string from a CUE line."""
    first_quote = line.find('"')
    if first_quote == -1:
        return ""
    second_quote = line.find('"', first_quote + 1)
    if second_quote == -1:
        return line[first_quote + 1 :]
    return line[first_quote + 1 : second_quote]


def _parse_cue(cue_path: str) -> CueData:
    """Parse a CUE sheet for album and track metadata."""
    path = Path(cue_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"CUE file not found: {cue_path}")

    album_title = ""
    album_artist = ""
    tracks: list[TrackInfo] = []
    current_number: int | None = None
    current_title = ""
    current_artist = ""

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue

            upper = line.upper()

            if upper.startswith("TRACK "):
                if current_number is not None:
                    tracks.append(
                        TrackInfo(
                            number=current_number,
                            title=current_title,
                            artist=current_artist or album_artist,
                        )
                    )
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        current_number = int(parts[1])
                    except ValueError:
                        current_number = len(tracks) + 1
                else:
                    current_number = len(tracks) + 1
                current_title = ""
                current_artist = ""
                continue

            if current_number is not None:
                if upper.startswith("TITLE "):
                    current_title = _extract_quoted(line)
                elif upper.startswith("PERFORMER "):
                    current_artist = _extract_quoted(line)
            else:
                if upper.startswith("TITLE "):
                    album_title = _extract_quoted(line)
                elif upper.startswith("PERFORMER "):
                    album_artist = _extract_quoted(line)

    if current_number is not None:
        tracks.append(
            TrackInfo(
                number=current_number,
                title=current_title,
                artist=current_artist or album_artist,
            )
        )

    return CueData(album_title=album_title, album_artist=album_artist, tracks=tracks)


def _audio_files_in_dir(track_dir: str) -> list[str]:
    """Return sorted list of supported audio files in the directory."""
    directory = Path(track_dir).expanduser()
    if not directory.is_dir():
        return []
    files = [
        str(p)
        for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_AUDIO_EXTS
    ]
    files.sort()
    return files


def _run_cuetag(cue_path: str, track_dir: str) -> list[str]:
    """Invoke cuetag on the audio files in ``track_dir``.

    Returns a list of warning messages.
    """
    warnings: list[str] = []
    files = _audio_files_in_dir(track_dir)
    if not files:
        warnings.append(f"No supported audio files found in {track_dir}")
        return warnings

    if not _check_cuetag_installed():
        warnings.append("cuetag not found in PATH; falling back to mutagen.")
        return warnings

    cmd = ["cuetag", cue_path, *files]
    try:
        _ = subprocess.run(cmd, check=False, capture_output=True, text=True)
    except Exception as exc:
        warnings.append(f"cuetag failed: {exc}")

    return warnings


def _write_flac_tags(
    file_path: str,
    title: str,
    artist: str,
    album: str,
    track_number: str,
) -> None:
    """Write Vorbis Comments to a FLAC file."""
    audio = FLAC(file_path)
    audio["TITLE"] = title
    audio["ARTIST"] = artist
    audio["ALBUM"] = album
    audio["TRACKNUMBER"] = track_number
    audio.save()


def _write_mp3_tags(
    file_path: str,
    title: str,
    artist: str,
    album: str,
    track_number: str,
) -> None:
    """Write ID3 tags to an MP3 file."""
    audio = MP3(file_path)
    tags = audio.tags
    if tags is None:
        audio.add_tags()
        tags = audio.tags
    if tags is None:
        raise RuntimeError(f"Could not create ID3 tags for {file_path}")
    tags["TIT2"] = TIT2(encoding=3, text=title)
    tags["TPE1"] = TPE1(encoding=3, text=artist)
    tags["TALB"] = TALB(encoding=3, text=album)
    tags["TRCK"] = TRCK(encoding=3, text=track_number)
    audio.save()


def _write_mutagen_tags(track_dir: str, cue_data: CueData) -> list[str]:
    """Write tags from parsed CUE data using mutagen.

    Handles FLAC (Vorbis Comments) and MP3 (ID3). Other formats are skipped.
    """
    warnings: list[str] = []
    files = _audio_files_in_dir(track_dir)
    if not files:
        warnings.append(f"No supported audio files found in {track_dir}")
        return warnings

    tracks = cue_data.tracks
    album_title = cue_data.album_title
    album_artist = cue_data.album_artist

    for index, file_path in enumerate(files):
        track = tracks[index] if index < len(tracks) else None
        title = track.title if track else ""
        artist = track.artist if track else album_artist
        track_number = str(track.number) if track else str(index + 1)

        path = Path(file_path)
        try:
            if path.suffix.lower() == ".flac":
                _write_flac_tags(
                    file_path, title, artist, album_title, track_number
                )
            elif path.suffix.lower() == ".mp3":
                _write_mp3_tags(
                    file_path, title, artist, album_title, track_number
                )
            else:
                warnings.append(
                    f"Mutagen fallback skipped unsupported format: {file_path}"
                )
        except Exception as exc:
            warnings.append(f"Failed to write tags to {file_path}: {exc}")

    return warnings


def _run_beets_import(
    track_dir: str,
    beets_config: str | None,
    beets_mode: str,
) -> list[str]:
    """Invoke ``beet import`` on the track directory.

    Returns a list of warning messages.
    """
    warnings: list[str] = []

    if not check_beets_installed():
        warnings.append("beet not found in PATH; skipping beets import.")
        return warnings

    config_path = _beets_config_path(beets_config)
    warnings.extend(_verify_beets_plugins(config_path))

    cmd: list[str] = ["beet"]
    if config_path:
        cmd.extend(["-c", str(config_path)])
    cmd.append("import")
    if beets_mode.lower() == "singleton":
        cmd.append("-s")
    cmd.append(track_dir)

    try:
        _ = subprocess.run(cmd, check=False, capture_output=True, text=True)
    except Exception as exc:
        warnings.append(f"beet import failed: {exc}")

    return warnings


def _get_tag_value(tags: TagContainer, keys: tuple[str, ...]) -> str:
    """Return the first non-empty tag value matching one of the keys."""
    for key in keys:
        value = tags.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            value = value[0] if value else ""
        elif hasattr(value, "text"):
            text = cast(object, getattr(value, "text"))
            if isinstance(text, list):
                value = text[0] if text else ""
            else:
                value = text
        if value:
            return str(value)
    return ""


def _verify_tags(track_dir: str) -> tuple[list[str], list[str], list[str]]:
    """Read back tags from each file and report missing required fields.

    Returns:
        (tagged_files, missing_tags, warnings)
    """
    tagged_files: list[str] = []
    missing_tags: list[str] = []
    warnings: list[str] = []

    files = _audio_files_in_dir(track_dir)
    if not files:
        warnings.append(
            f"No supported audio files found in {track_dir} for verification"
        )
        return tagged_files, missing_tags, warnings

    for file_path in files:
        try:
            audio: object = MutagenFile(file_path)
        except Exception as exc:
            warnings.append(f"Could not read tags from {file_path}: {exc}")
            continue

        if audio is None:
            missing_tags.append(f"{file_path} missing all tags")
            continue

        tags = getattr(audio, "tags", None)
        if tags is None or not isinstance(tags, TagContainer):
            missing_tags.append(f"{file_path} missing all tags")
            continue

        tagged_files.append(file_path)
        for field_name, keys in REQUIRED_TAG_FIELDS.items():
            value = _get_tag_value(tags, keys)
            if not value:
                missing_tags.append(f"{file_path} missing {field_name}")

    return tagged_files, missing_tags, warnings


def tag_tracks(
    track_dir: str,
    cue_path: str,
    beets_config: str | None = None,
    use_beets: bool = True,
    beets_mode: str = "album",
) -> TagResult:
    """Tag split audio files using cuetag (or mutagen fallback) and optional beets.

    Args:
        track_dir: Directory containing the split audio files.
        cue_path: CUE sheet providing track and album metadata.
        beets_config: Optional path to a beets configuration file.
        use_beets: Whether to invoke ``beet import`` after tagging.
        beets_mode: beets import mode, ``album`` or ``singleton``.

    Returns:
        A ``TagResult`` summarising the operation.
    """
    result = TagResult()

    if not Path(track_dir).expanduser().is_dir():
        result.warnings.append(f"Track directory not found: {track_dir}")
        return result

    if not Path(cue_path).expanduser().exists():
        result.warnings.append(f"CUE file not found: {cue_path}")
        return result

    cuetag_warnings = _run_cuetag(cue_path, track_dir)
    result.warnings.extend(cuetag_warnings)

    if any("cuetag not found in PATH" in w for w in cuetag_warnings):
        try:
            cue_data = _parse_cue(cue_path)
        except Exception as exc:
            result.warnings.append(f"Failed to parse CUE for mutagen fallback: {exc}")
            cue_data = CueData(album_title="", album_artist="", tracks=[])
        mutagen_warnings = _write_mutagen_tags(track_dir, cue_data)
        result.warnings.extend(mutagen_warnings)

    if use_beets:
        beets_warnings = _run_beets_import(track_dir, beets_config, beets_mode)
        result.warnings.extend(beets_warnings)

    tagged_files, missing_tags, verify_warnings = _verify_tags(track_dir)
    result.tagged_files = tagged_files
    result.missing_tags = missing_tags
    result.warnings.extend(verify_warnings)

    result.success = bool(result.tagged_files) and not any(
        "Failed to write tags" in w or "cuetag failed" in w for w in result.warnings
    )
    return result
