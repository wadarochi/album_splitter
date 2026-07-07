"""Post-split cleanup: remove pregap/short tracks and renumber remaining files."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import soundfile


_AUDIO_EXTS = {".flac", ".wav", ".ape", ".mp3", ".m4a", ".ogg", ".opus"}
_TRACK_RE = re.compile(r"^(\d+)\s*-\s*(.+?)(\.\w+)$")


@dataclass(frozen=True)
class CleanupAction:
    """Record of a single cleanup operation."""

    old_path: Path
    new_path: Path | None
    reason: str


def _audio_duration(path: Path) -> float:
    """Return audio duration in seconds, falling back to 0 on error."""
    suffix = path.suffix.lower()
    try:
        if suffix in (".flac", ".wav"):
            with soundfile.SoundFile(str(path)) as sf:
                return sf.frames / sf.samplerate
    except Exception:
        pass
    try:
        from mutagen import File as MutagenFile

        audio = MutagenFile(str(path))
        if audio is not None and audio.info.length:
            return float(audio.info.length)
    except Exception:
        pass
    return 0.0


def _parse_track_filename(path: Path) -> tuple[int, str, str] | None:
    """Parse ``NN - Title.ext`` into (number, title, extension) or None."""
    match = _TRACK_RE.match(path.name)
    if not match:
        return None
    number = int(match.group(1))
    title = match.group(2).strip()
    ext = match.group(3).lower()
    return number, title, ext


def cleanup_tracks(
    track_dir: str | Path,
    min_duration: float = 10.0,
    remove_pregap: bool = True,
    dry_run: bool = False,
    progress_callback: Callable[[str], None] | None = None,
) -> list[CleanupAction]:
    """Remove pregap/short tracks and renumber the remaining files.

    Files matching ``NN - Title.ext`` are considered tracks. Pregap files are
    identified as track number 0 with a title containing "pregap" or "silence".
    Short tracks have a duration below ``min_duration`` seconds.

    After removals, surviving tracks are renumbered sequentially starting at 1.
    Files that do not match the naming pattern are left untouched.

    Args:
        track_dir: Directory containing split track files.
        min_duration: Drop tracks shorter than this many seconds. Set to 0 to
            disable duration-based removal (pregap removal still applies).
        remove_pregap: Drop track-0 files named pregap/silence.
        dry_run: Log planned actions without renaming or deleting files.
        progress_callback: Optional callable receiving status messages.

    Returns:
        List of cleanup actions performed (or planned in dry-run mode).
    """
    directory = Path(track_dir).expanduser()
    if not directory.is_dir():
        raise NotADirectoryError(f"Not a directory: {directory}")

    def log(msg: str) -> None:
        if progress_callback:
            progress_callback(msg)

    # Collect candidate audio files that match the expected naming pattern.
    tracks: list[tuple[Path, int, str, str, float]] = []
    skipped: list[Path] = []
    for path in sorted(directory.iterdir()):
        if not path.is_file() or path.suffix.lower() not in _AUDIO_EXTS:
            continue
        parsed = _parse_track_filename(path)
        if parsed is None:
            skipped.append(path)
            continue
        number, title, ext = parsed
        duration = _audio_duration(path)
        tracks.append((path, number, title, ext, duration))

    if not tracks:
        log("No track-like audio files found.")
        return []

    # Decide which tracks to keep.
    keep: list[tuple[Path, int, str, str, float]] = []
    removed: list[tuple[Path, str]] = []
    for path, number, title, ext, duration in tracks:
        is_pregap = remove_pregap and number == 0 and (
            "pregap" in title.lower() or "silence" in title.lower()
        )
        is_short = min_duration > 0 and duration < min_duration
        if is_pregap:
            removed.append((path, f"pregap (duration {duration:.1f}s)"))
        elif is_short:
            removed.append((path, f"short ({duration:.1f}s < {min_duration:.1f}s)"))
        else:
            keep.append((path, number, title, ext, duration))

    # Sort kept tracks by original track number, then by filename for stability.
    keep.sort(key=lambda item: (item[1], item[0].name))

    actions: list[CleanupAction] = []

    # Remove unwanted files.
    for path, reason in removed:
        log(f"Removing {path.name}: {reason}")
        actions.append(CleanupAction(old_path=path, new_path=None, reason=reason))
        if not dry_run:
            path.unlink()

    regular_tracks = [item for item in keep if item[1] > 0]

    for new_index, (path, _old_number, title, ext, _duration) in enumerate(regular_tracks, start=1):
        new_name = f"{new_index:02d} - {title}{ext}"
        new_path = directory / new_name
        if path.name == new_name:
            continue
        log(f"Renaming {path.name} -> {new_name}")
        actions.append(
            CleanupAction(old_path=path, new_path=new_path, reason="renumber")
        )
        if not dry_run:
            path.rename(new_path)

    if dry_run:
        log(f"Dry run: would remove {len(removed)} and renumber {len(keep)} tracks.")
    else:
        log(f"Removed {len(removed)} tracks, kept {len(keep)} tracks.")

    return actions
