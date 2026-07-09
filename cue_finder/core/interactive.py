"""Interactive candidate selection for album metadata."""

from __future__ import annotations

import sys
from typing import Callable

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from cue_finder.core.match import TrackMatcher
from cue_finder.core.rank import AlbumScore
from cue_finder.core.search import AlbumInfo

_SCORE_THRESHOLD = 0.50
_SCORE_GAP_THRESHOLD = 0.10
_MAX_DISPLAY = 10
_DISC_SPLIT_RATIO = 1.5
_DISC_SPLIT_MIN_DIFF = 3


class SelectionAborted(Exception):
    """User aborted the selection process."""


def should_prompt(scored: list[AlbumScore]) -> bool:
    """Decide whether user intervention is warranted."""
    if not scored:
        return False
    if scored[0].total_score < _SCORE_THRESHOLD:
        return True
    if len(scored) > 1 and (scored[0].total_score - scored[1].total_score) < _SCORE_GAP_THRESHOLD:
        return True
    if scored[0].flags:
        return True
    return False


def should_split_disc(album: AlbumInfo, n_detected: int) -> bool:
    """Check if album track count suggests a multi-disc release."""
    if n_detected <= 0:
        return False
    n_meta = len(album.tracks)
    if n_meta < n_detected * _DISC_SPLIT_RATIO:
        return False
    if n_meta - n_detected < _DISC_SPLIT_MIN_DIFF:
        return False
    return True


def parse_range(text: str) -> tuple[int, int] | None:
    """Parse '1-10' or '1:10' into (start, end). Returns None on failure."""
    text = text.strip()
    for sep in ("-", ":"):
        if sep in text:
            parts = text.split(sep, 1)
            try:
                return (int(parts[0]), int(parts[1]))
            except ValueError:
                return None
    try:
        n = int(text)
        return (n, n)
    except ValueError:
        return None


def create_disc_subset(album: AlbumInfo, start: int, end: int) -> AlbumInfo:
    """Create a new AlbumInfo containing only tracks[start-1:end]."""
    tracks = album.tracks[start - 1 : end]
    return AlbumInfo(
        artist=album.artist,
        title=f"{album.title} (disc {start}-{end})",
        date=album.date,
        source=album.source,
        source_id=album.source_id,
        tracks=tracks,
    )


def select_album(
    scored: list[AlbumScore],
    interactive: bool | None,
    query: str,
    boundaries: list[float],
    total_duration: float,
    console: Console | None = None,
    search_fn: Callable[[str], list[AlbumScore]] | None = None,
) -> AlbumInfo | None:
    """Select the best album candidate, optionally prompting the user."""
    if not scored:
        raise ValueError("No candidates to select from.")

    if interactive is False:
        return scored[0].album

    if interactive is None and not should_prompt(scored):
        return scored[0].album

    console = console or Console()

    if not sys.stdin.isatty():
        console.print("[dim]Non-interactive terminal: auto-selecting best candidate.[/dim]")
        return scored[0].album

    album = _interactive_loop(scored, query, boundaries, total_duration, console, search_fn)
    if album is None:
        return None

    n_detected = len(boundaries) + 1 if boundaries else 0
    if n_detected > 0:
        album = _maybe_split_disc(album, n_detected, console)

    return album


def _interactive_loop(
    scored: list[AlbumScore],
    query: str,
    boundaries: list[float],
    total_duration: float,
    console: Console,
    search_fn: Callable[[str], list[AlbumScore]] | None,
) -> AlbumInfo | None:
    while True:
        _display_candidates(scored, query, boundaries, total_duration, console)

        n = min(len(scored), _MAX_DISPLAY)
        prompt = f"Select [1-{n}], (d)etail, (s)kip, (m)anual, (q)uit"
        selection = Prompt.ask(prompt, default="1")
        selection = selection.strip().lower()

        if selection == "" or selection == "1":
            return scored[0].album

        if selection in ("d", "detail"):
            _detail_subloop(scored, boundaries, total_duration, console)
            continue

        if selection in ("s", "skip"):
            return None

        if selection in ("m", "manual"):
            if search_fn is None:
                console.print("[yellow]Manual search not available.[/yellow]")
                continue
            new_query = Prompt.ask("Enter search query", default=query)
            new_scored = search_fn(new_query)
            if new_scored:
                scored = new_scored
                query = new_query
            continue

        if selection in ("q", "quit"):
            raise SelectionAborted("User aborted selection.")

        try:
            idx = int(selection)
            if 1 <= idx <= n:
                return scored[idx - 1].album
        except ValueError:
            pass

        console.print(f"[red]Invalid choice: {selection}[/red]")


def _display_candidates(
    scored: list[AlbumScore],
    query: str,
    boundaries: list[float],
    total_duration: float,
    console: Console,
) -> None:
    n_segments = len(boundaries) + 1
    total_mins = int(total_duration // 60)
    total_secs = int(total_duration % 60)

    table = Table(
        title=f'Candidates for "{query}"  ({n_segments} tracks, {total_mins}:{total_secs:02d} total)',
    )
    table.add_column("#", style="bold", width=3)
    table.add_column("Artist", ratio=2)
    table.add_column("Album", ratio=2)
    table.add_column("Year", width=6)
    table.add_column("Trk", width=4, justify="right")
    table.add_column("Source", width=10)
    table.add_column("Score", width=6, justify="right")
    table.add_column("Flags", width=12)

    for i, score in enumerate(scored[:_MAX_DISPLAY], 1):
        album = score.album
        score_style = _score_style(score.total_score)
        flag_str = _format_flags(score.flags, score.count_delta)
        table.add_row(
            str(i),
            album.artist,
            album.title,
            album.date[:4] if album.date else "—",
            str(len(album.tracks)),
            album.source,
            f"[{score_style}]{score.total_score:.2f}[/{score_style}]",
            flag_str,
        )

    console.print(table)


def _score_style(score: float) -> str:
    if score >= 0.6:
        return "green"
    if score >= 0.4:
        return "yellow"
    return "red"


def _format_flags(flags: list[str], count_delta: int) -> str:
    parts: list[str] = []
    if "track_count_mismatch" in flags:
        parts.append(f"count!Δ{count_delta}")
    if "duration_mismatch" in flags:
        parts.append("dur!")
    return " ".join(parts) if parts else "—"


def _detail_subloop(
    scored: list[AlbumScore],
    boundaries: list[float],
    total_duration: float,
    console: Console,
) -> None:
    n = min(len(scored), _MAX_DISPLAY)
    selection = Prompt.ask(f"Detail for which candidate [1-{n}]", default="1")

    try:
        idx = int(selection.strip())
    except ValueError:
        console.print("[red]Invalid selection.[/red]")
        return

    if idx < 1 or idx > n:
        console.print("[red]Invalid selection.[/red]")
        return

    _display_detail(scored[idx - 1], boundaries, total_duration, console)
    _ = Prompt.ask("Press Enter to go back", default="")


def _display_detail(
    score: AlbumScore,
    boundaries: list[float],
    total_duration: float,
    console: Console,
) -> None:
    album = score.album
    header = (
        f"{album.artist} — {album.title}\n"
        f"source={album.source}, total_score={score.total_score:.2f}, "
        f"text_tier={score.text_tier}, duration_score={score.duration_score:.2f}, "
        f"count_delta={score.count_delta}, fingerprint_hit={score.fingerprint_hit}"
    )
    console.print(Panel(header, title="Album Detail"))

    track_durations = [t.duration_sec or 0.0 for t in album.tracks]
    track_titles = [t.title for t in album.tracks]
    track_artists = [t.artist or album.artist for t in album.tracks]

    try:
        matches = TrackMatcher().match(
            boundaries,
            track_durations,
            track_titles,
            track_artists,
            total_duration,
        )
    except Exception:
        console.print("[yellow]Could not compute track alignment.[/yellow]")
        return

    if not matches:
        console.print("[yellow]Could not compute track alignment.[/yellow]")
        return

    table = Table(title="Track Alignment")
    table.add_column("#", width=3)
    table.add_column("Title")
    table.add_column("Expected", width=8, justify="right")
    table.add_column("Actual", width=8, justify="right")
    table.add_column("Conf", width=6, justify="right")
    table.add_column("Flags")

    for match in matches:
        conf_style = _confidence_style(match.confidence)
        flag_str = ", ".join(match.flags) if match.flags else "—"
        table.add_row(
            str(match.number),
            match.title,
            _format_duration(match.expected_duration),
            _format_duration(match.actual_duration),
            f"[{conf_style}]{match.confidence:.2f}[/{conf_style}]",
            flag_str,
        )

    console.print(table)


def _confidence_style(confidence: float) -> str:
    if confidence >= 0.8:
        return "green"
    if confidence >= 0.5:
        return "yellow"
    return "red"


def _format_duration(seconds: float) -> str:
    if seconds <= 0:
        return "—"
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins}:{secs:02d}"


def _suggest_disc_ranges(n_meta: int, n_detected: int) -> list[tuple[str, int, int]]:
    """Build suggested (label, start, end) tuples for disc splitting."""
    raw: list[tuple[str, int, int]] = []
    raw.append(("Disc 1", 1, min(n_detected, n_meta)))
    if n_meta > n_detected:
        raw.append(("Disc 2", n_detected + 1, n_meta))
    half = n_meta // 2
    if half > 0 and half != n_detected:
        raw.append(("First half", 1, half))
        if half + 1 <= n_meta:
            raw.append(("Second half", half + 1, n_meta))
    seen: set[tuple[int, int]] = set()
    unique: list[tuple[str, int, int]] = []
    for label, start, end in raw:
        key = (start, end)
        if key not in seen and start >= 1 and end <= n_meta and start <= end:
            seen.add(key)
            unique.append((label, start, end))
    return unique


def _maybe_split_disc(
    album: AlbumInfo,
    n_detected: int,
    console: Console,
) -> AlbumInfo:
    """Offer disc-range selection when album track count far exceeds detected."""
    if not should_split_disc(album, n_detected):
        return album
    if not sys.stdin.isatty():
        return album

    n_meta = len(album.tracks)
    console.print()
    console.print(
        f"[bold yellow]Track count mismatch:[/bold yellow] Album has {n_meta} tracks, but {n_detected} segments detected."
    )
    console.print("This may be a multi-disc album. Select a track subset.")
    console.print()

    suggestions = _suggest_disc_ranges(n_meta, n_detected)
    for i, (label, start, end) in enumerate(suggestions, 1):
        count = end - start + 1
        marker = " [green]<- matches detected[/green]" if count == n_detected else ""
        console.print(f"  {i}. {label}: tracks {start}-{end} ({count} tracks){marker}")
    console.print(f"  a. All {n_meta} tracks")

    selection = Prompt.ask("Select [1-N], enter range (e.g. 3-12), or 'a'", default="1")
    selection = selection.strip().lower()

    if selection == "a":
        return album

    try:
        idx = int(selection)
        if 1 <= idx <= len(suggestions):
            _, start, end = suggestions[idx - 1]
            console.print(f"  [green]Selected tracks {start}-{end} ({end - start + 1} tracks)[/green]")
            return create_disc_subset(album, start, end)
    except ValueError:
        pass

    parsed = parse_range(selection)
    if parsed:
        start, end = parsed
        if 1 <= start <= end <= n_meta:
            console.print(f"  [green]Selected tracks {start}-{end} ({end - start + 1} tracks)[/green]")
            return create_disc_subset(album, start, end)

    console.print("[red]Invalid selection. Using all tracks.[/red]")
    return album
