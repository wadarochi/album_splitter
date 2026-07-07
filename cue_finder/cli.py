"""cue-finder CLI entry point — dual-mode: non-interactive subcommands and Textual TUI."""

import json
import logging
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

app = typer.Typer(
    name="cue-finder",
    help="End-to-end CLI tool for splitting single-file CD rips into individual tracks with metadata tagging.",
    add_completion=False,
)

console = Console()
logger = logging.getLogger("cue-finder")

EXIT_OK = 0
EXIT_PARTIAL = 1
EXIT_FAILURE = 2
EXIT_INVALID_ARGS = 3
EXIT_MISSING_DEPS = 4


def _setup_logging(verbose: bool, quiet: bool) -> None:
    if quiet:
        level = logging.WARNING
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )


@app.callback()
def callback(
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable verbose (DEBUG) logging."
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress non-error output (WARNING level)."
    ),
    interactive: Optional[bool] = typer.Option(
        None, "--interactive/--no-interactive", help="Force interactive or non-interactive mode."
    ),
) -> None:
    """cue-finder: Split single-file CD rips into individual tracks with metadata tagging."""
    _setup_logging(verbose, quiet)


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query (e.g., 'Artist Album')."),
    source: Optional[str] = typer.Option(
        None, "--source", "-s", help="Filter by source (musicbrainz, itunes, netease, discogs, deezer, gnudb)."
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output results as JSON instead of Rich table."
    ),
) -> None:
    """Search album metadata across multiple sources."""
    from cue_finder.core.search import AlbumInfo, search_album

    sources = [source] if source else None
    try:
        results = search_album(query, sources=sources)
    except Exception as exc:
        logger.error("Search failed: %s", exc)
        console.print(Panel(f"Search failed: {exc}", title="Error", border_style="red"))
        raise typer.Exit(EXIT_FAILURE)

    if not results:
        console.print("[yellow]No results found.[/yellow]")
        return

    if json_output:
        console.print_json(data=[_album_to_dict(r) for r in results])
    else:
        table = Table(title=f"Search results for: {query}")
        table.add_column("#", style="dim")
        table.add_column("Album")
        table.add_column("Artist")
        table.add_column("Year")
        table.add_column("Tracks")
        table.add_column("Source")
        for i, album in enumerate(results, 1):
            table.add_row(
                str(i),
                album.title,
                album.artist,
                album.date or "—",
                str(len(album.tracks)),
                album.source,
            )
        console.print(table)


def _album_to_dict(album: "AlbumInfo") -> dict:
    return {
        "artist": album.artist,
        "title": album.title,
        "date": album.date,
        "source": album.source,
        "source_id": album.source_id,
        "tracks": [
            {"title": t.title, "duration_sec": t.duration_sec, "artist": t.artist}
            for t in album.tracks
        ],
    }


@app.command()
def detect(
    input_file: str = typer.Option(..., "-i", "--input", help="Input audio file path."),
    threshold: float = typer.Option(-40.0, "--threshold", help="Silence threshold in dB."),
    min_length: int = typer.Option(5000, "--min-length", help="Minimum track length in ms."),
    min_interval: int = typer.Option(300, "--min-interval", help="Minimum silence interval in ms."),
    hop_size: int = typer.Option(10, "--hop-size", help="Hop size in ms."),
    max_sil_kept: int = typer.Option(500, "--max-sil-kept", help="Max silence kept in ms."),
    output: Optional[str] = typer.Option(None, "-o", "--output", help="Output JSON file path."),
) -> None:
    """Detect track boundaries via silence detection."""
    from cue_finder.core.silence import SilenceDetector

    input_path = Path(input_file).expanduser()
    if not input_path.exists():
        console.print(Panel(f"File not found: {input_file}", title="Error", border_style="red"))
        raise typer.Exit(EXIT_INVALID_ARGS)

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
        transient=True, console=console,
    ) as progress:
        task_id = progress.add_task("Detecting boundaries...", total=None)
        try:
            detector = SilenceDetector(
                threshold=threshold, min_length=min_length,
                min_interval=min_interval, hop_size=hop_size,
                max_sil_kept=max_sil_kept,
            )
            boundaries = detector.detect_boundaries(str(input_path))
        except ValueError as exc:
            progress.stop()
            console.print(Panel(str(exc), title="Invalid Parameters", border_style="red"))
            raise typer.Exit(EXIT_INVALID_ARGS)
        except Exception as exc:
            progress.stop()
            logger.error("Detection failed: %s", exc)
            console.print(Panel(f"Detection failed: {exc}", title="Error", border_style="red"))
            raise typer.Exit(EXIT_FAILURE)
        progress.update(task_id, visible=False)

    if output:
        Path(output).write_text(json.dumps(boundaries, indent=2), encoding="utf-8")
        console.print(f"[green]Boundaries written to {output}[/green]")
    else:
        console.print_json(data=boundaries)

    console.print(f"[bold]Found {len(boundaries)} boundaries ({len(boundaries) + 1} tracks)[/bold]")


@app.command()
def generate(
    input_file: str = typer.Option(..., "-i", "--input", help="Input audio file path."),
    tracklist_file: Optional[str] = typer.Option(None, "--tracklist", help="YAML or plain text tracklist file."),
    search_query: Optional[str] = typer.Option(None, "--search", help="Search query for metadata lookup."),
    output: str = typer.Option(..., "-o", "--output", help="Output CUE file path."),
    source: Optional[str] = typer.Option(None, "--source", "-s", help="Metadata source(s), comma-separated (musicbrainz,itunes,netease,discogs,deezer,gnudb)."),
) -> None:
    """Generate a CUE sheet from detected boundaries and metadata."""
    from cue_finder.core.cue import CueTrack, generate_cue, seconds_to_msf, write_cue
    from cue_finder.core.match import TrackMatcher
    from cue_finder.core.silence import SilenceDetector
    from cue_finder.core.search import search_album
    from cue_finder.core.tracklist import detect_format, load_tracklist, parse_plain_text
    import soundfile

    input_path = Path(input_file).expanduser()
    if not input_path.exists():
        console.print(Panel(f"File not found: {input_file}", title="Error", border_style="red"))
        raise typer.Exit(EXIT_INVALID_ARGS)

    # Detect boundaries
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  transient=True, console=console) as progress:
        progress.add_task("Detecting boundaries...", total=None)
        detector = SilenceDetector()
        boundaries = detector.detect_boundaries(str(input_path))

    # Get audio info
    with soundfile.SoundFile(str(input_path)) as sf:
        sample_rate = sf.samplerate
        total_duration = sf.frames / sample_rate

    # Get track info from tracklist or search
    if tracklist_file:
        fmt = detect_format(Path(tracklist_file))
        if fmt == "yaml":
            tl = load_tracklist(Path(tracklist_file))
            track_titles = [t.title for t in tl.tracks]
            track_durations = [t.duration or 0.0 for t in tl.tracks]
            track_artists = [t.artist or tl.album.artist for t in tl.tracks]
            album_artist = tl.album.artist
            album_title = tl.album.title
        else:
            text = Path(tracklist_file).read_text(encoding="utf-8")
            tl = parse_plain_text(text)
            track_titles = [t.title for t in tl.tracks]
            track_durations = [0.0] * len(tl.tracks)
            track_artists = [""] * len(tl.tracks)
            album_artist = ""
            album_title = ""
    elif search_query:
        sources = [s.strip() for s in source.split(",") if s.strip()] if source else None
        results = search_album(search_query, sources=sources)
        if not results:
            console.print("[yellow]No metadata found for query.[/yellow]")
            raise typer.Exit(EXIT_PARTIAL)
        album = results[0]
        track_titles = [t.title for t in album.tracks]
        track_durations = [t.duration_sec for t in album.tracks]
        track_artists = [t.artist or album.artist for t in album.tracks]
        album_artist = album.artist
        album_title = album.title
    else:
        console.print(Panel("Provide --tracklist or --search", title="Error", border_style="red"))
        raise typer.Exit(EXIT_INVALID_ARGS)

    # Match
    matcher = TrackMatcher()
    matches = matcher.match(boundaries, track_durations, track_titles, track_artists, total_duration)

    # Generate CUE
    cue_tracks = [
        CueTrack(
            track_number=m.number,
            title=m.title,
            performer=m.artist,
            index01=seconds_to_msf(m.start, sample_rate),
            start_seconds=m.start,
        )
        for m in matches
    ]
    cue_text = generate_cue(
        album_artist=album_artist,
        album_title=album_title,
        audio_filename=input_path.name,
        matched_tracks=cue_tracks,
    )
    write_cue(cue_text, output)
    console.print(f"[green]CUE sheet written to {output}[/green]")


@app.command()
def split(
    input_file: str = typer.Option(..., "-i", "--input", help="Input audio file path."),
    cue_file: Optional[str] = typer.Option(None, "-c", "--cue", help="CUE file for split points."),
    timestamps: Optional[str] = typer.Option(None, "--timestamps", help="Comma-separated timestamps in seconds."),
    output_dir: str = typer.Option(..., "-o", "--output", help="Output directory for split files."),
    format: Optional[str] = typer.Option(None, "--format", help="Output audio format (flac, wav)."),
    name_template: Optional[str] = typer.Option(None, "--name-template", help="Output filename template."),
) -> None:
    """Split audio file into individual tracks."""
    from cue_finder.core.split import Splitter

    input_path = Path(input_file).expanduser()
    if not input_path.exists():
        console.print(Panel(f"File not found: {input_file}", title="Error", border_style="red"))
        raise typer.Exit(EXIT_INVALID_ARGS)

    ts_list: Optional[list[float]] = None
    if timestamps:
        try:
            ts_list = [float(t.strip()) for t in timestamps.split(",") if t.strip()]
        except ValueError:
            console.print(Panel("Invalid timestamps format.", title="Error", border_style="red"))
            raise typer.Exit(EXIT_INVALID_ARGS)

    splitter = Splitter()
    splitter.report_backends()

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
        transient=True, console=console,
    ) as progress:
        task_id = progress.add_task("Splitting audio...", total=None)
        try:
            paths = splitter.split(
                str(input_path),
                cue_path_or_timestamps=cue_file if cue_file else ts_list,
                output_dir=output_dir,
                format=format,
                name_template=name_template,
            )
        except Exception as exc:
            progress.stop()
            logger.error("Split failed: %s", exc)
            console.print(Panel(f"Split failed: {exc}", title="Error", border_style="red"))
            raise typer.Exit(EXIT_FAILURE)
        progress.update(task_id, visible=False)

    console.print(f"[green]Split into {len(paths)} files in {output_dir}[/green]")


@app.command()
def tag(
    track_dir: str = typer.Option(..., "-d", "--track-dir", help="Directory containing split track files."),
    cue_file: str = typer.Option(..., "-c", "--cue", help="CUE file for metadata."),
    use_beets: bool = typer.Option(True, "--beets/--no-beets", help="Use beets for tagging."),
    beets_config: Optional[str] = typer.Option(None, "--beets-config", help="Custom beets config file path."),
    beets_mode: str = typer.Option("album", "--beets-mode", help="beets import mode: album or singleton."),
) -> None:
    """Tag split track files with metadata."""
    from cue_finder.core.tag import tag_tracks

    result = tag_tracks(
        track_dir=track_dir,
        cue_path=cue_file,
        beets_config=beets_config,
        use_beets=use_beets,
        beets_mode=beets_mode,
    )

    if result.warnings:
        for w in result.warnings:
            console.print(f"[yellow]⚠ {w}[/yellow]")
    if result.missing_tags:
        for m in result.missing_tags:
            console.print(f"[red]✗ {m}[/red]")

    if result.success:
        console.print(f"[green]Tagged {len(result.tagged_files)} files.[/green]")
    else:
        console.print("[yellow]Tagging completed with warnings.[/yellow]")


@app.command()
def cleanup_pregap(
    track_dir: str = typer.Option(..., "-d", "--track-dir", help="Directory containing split track files."),
    min_duration: float = typer.Option(0.0, "--min-duration", help="Also drop tracks shorter than this many seconds (0 = disabled)."),
    keep_pregap: bool = typer.Option(False, "--keep-pregap", help="Keep track-0 files named pregap/silence."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be done without changing files."),
) -> None:
    """Remove pregap/short tracks and renumber remaining files."""
    from cue_finder.core.cleanup import cleanup_tracks

    try:
        actions = cleanup_tracks(
            track_dir=track_dir,
            min_duration=min_duration,
            remove_pregap=not keep_pregap,
            dry_run=dry_run,
            progress_callback=lambda msg: console.print(f"  {msg}"),
        )
    except Exception as exc:
        logger.error("Cleanup failed: %s", exc)
        console.print(Panel(f"Cleanup failed: {exc}", title="Error", border_style="red"))
        raise typer.Exit(EXIT_FAILURE)

    if dry_run:
        console.print(f"[yellow]Dry run: {len(actions)} actions planned.[/yellow]")
    elif actions:
        console.print(f"[green]Cleaned up {len(actions)} files.[/green]")
    else:
        console.print("[dim]No cleanup actions needed.[/dim]")


@app.command()
def run(
    input_file: str = typer.Option(..., "-i", "--input", help="Input audio file path."),
    search_query: Optional[str] = typer.Option(None, "--search", help="Search query for metadata."),
    tracklist: Optional[str] = typer.Option(None, "--tracklist", help="YAML or plain text tracklist file."),
    output_dir: str = typer.Option(..., "-o", "--output", help="Output directory."),
    format: Optional[str] = typer.Option(None, "--format", help="Output audio format."),
    source: Optional[str] = typer.Option(None, "--source", "-s", help="Metadata source(s), comma-separated (musicbrainz,itunes,netease,discogs,deezer,gnudb)."),
    threshold: float = typer.Option(-40.0, "--threshold", help="Silence threshold in dB."),
    min_length: int = typer.Option(5000, "--min-length", help="Minimum track length in ms."),
    min_interval: int = typer.Option(300, "--min-interval", help="Minimum silence interval in ms."),
    hop_size: int = typer.Option(10, "--hop-size", help="Hop size in ms."),
    max_sil_kept: int = typer.Option(500, "--max-sil-kept", help="Max silence kept in ms."),
    use_beets: bool = typer.Option(True, "--beets/--no-beets", help="Use beets for tagging."),
    beets_config: Optional[str] = typer.Option(None, "--beets-config", help="Custom beets config file path."),
    beets_mode: str = typer.Option("album", "--beets-mode", help="beets import mode."),
    cleanup_pregap_flag: bool = typer.Option(False, "--cleanup-pregap", help="Remove pregap/short tracks after splitting."),
    min_track_duration: float = typer.Option(0.0, "--min-track-duration", help="Also drop tracks shorter than this many seconds when --cleanup-pregap is used (0 = disabled)."),
) -> None:
    """Run the full pipeline: detect -> search -> match -> generate CUE -> split -> tag -> optional cleanup."""
    import soundfile
    from cue_finder.core.cleanup import cleanup_tracks
    from cue_finder.core.cue import CueTrack, generate_cue, seconds_to_msf, write_cue
    from cue_finder.core.match import TrackMatcher
    from cue_finder.core.silence import SilenceDetector
    from cue_finder.core.search import search_album
    from cue_finder.core.split import Splitter
    from cue_finder.core.tag import tag_tracks
    from cue_finder.core.tracklist import detect_format, load_tracklist, parse_plain_text

    input_path = Path(input_file).expanduser()
    if not input_path.exists() or not input_path.is_file():
        console.print(Panel(f"File not found: {input_file}", title="Error", border_style="red"))
        raise typer.Exit(EXIT_INVALID_ARGS)

    out_dir = Path(output_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Detect
    console.print("[bold]Step 1/5: Detecting silence boundaries...[/bold]")
    detector = SilenceDetector(
        threshold=threshold, min_length=min_length, min_interval=min_interval,
        hop_size=hop_size, max_sil_kept=max_sil_kept,
    )
    boundaries = detector.detect_boundaries(str(input_path))
    console.print(f"  Found {len(boundaries)} boundaries ({len(boundaries) + 1} tracks)")

    # Get audio info
    with soundfile.SoundFile(str(input_path)) as sf:
        sample_rate = sf.samplerate
        total_duration = sf.frames / sample_rate

    # Step 2: Metadata
    console.print("[bold]Step 2/5: Searching metadata...[/bold]")
    if tracklist:
        fmt = detect_format(Path(tracklist))
        if fmt == "yaml":
            tl = load_tracklist(Path(tracklist))
            track_titles = [t.title for t in tl.tracks]
            track_durations = [t.duration or total_duration / len(tl.tracks) for t in tl.tracks]
            track_artists = [t.artist or tl.album.artist for t in tl.tracks]
            album_artist = tl.album.artist
            album_title = tl.album.title
        else:
            text = Path(tracklist).read_text(encoding="utf-8")
            tl = parse_plain_text(text)
            track_titles = [t.title for t in tl.tracks]
            track_durations = [total_duration / len(tl.tracks)] * len(tl.tracks)
            track_artists = [""] * len(tl.tracks)
            album_artist = ""
            album_title = ""
    elif search_query:
        sources = [s.strip() for s in source.split(",") if s.strip()] if source else None
        results = search_album(search_query, sources=sources)
        if not results:
            console.print("[yellow]No metadata found. Using numbered tracks.[/yellow]")
            n = len(boundaries) + 1
            track_titles = [f"Track {i:02d}" for i in range(1, n + 1)]
            track_durations = [total_duration / n] * n
            track_artists = [""] * n
            album_artist = ""
            album_title = input_path.stem
        else:
            album = results[0]
            console.print(f"  Matched: {album.artist} — {album.title} ({album.source})")
            track_titles = [t.title for t in album.tracks]
            track_durations = [t.duration_sec for t in album.tracks]
            track_artists = [t.artist or album.artist for t in album.tracks]
            album_artist = album.artist
            album_title = album.title
    else:
        n = len(boundaries) + 1
        track_titles = [f"Track {i:02d}" for i in range(1, n + 1)]
        track_durations = [total_duration / n] * n
        track_artists = [""] * n
        album_artist = ""
        album_title = input_path.stem

    # Step 3: Match
    console.print("[bold]Step 3/5: Matching tracks...[/bold]")
    matcher = TrackMatcher()
    matches = matcher.match(boundaries, track_durations, track_titles, track_artists, total_duration)
    for m in matches:
        flags = f"[dim]({', '.join(m.flags)})[/dim]" if m.flags else ""
        console.print(f"  {m.number:02d}: {m.title} [{m.start:.1f}s–{m.end:.1f}s] conf={m.confidence:.2f} {flags}")

    # Step 4: Generate CUE
    console.print("[bold]Step 4/5: Generating CUE sheet...[/bold]")
    cue_path = out_dir / f"{input_path.stem}.cue"
    cue_tracks = [
        CueTrack(
            track_number=m.number,
            title=m.title,
            performer=m.artist,
            index01=seconds_to_msf(m.start, sample_rate),
            start_seconds=m.start,
        )
        for m in matches
    ]
    cue_text = generate_cue(
        album_artist=album_artist,
        album_title=album_title,
        audio_filename=input_path.name,
        matched_tracks=cue_tracks,
    )
    write_cue(cue_text, str(cue_path))
    console.print(f"  Wrote CUE: {cue_path}")

    # Step 5: Split + Tag
    console.print("[bold]Step 5/5: Splitting and tagging...[/bold]")
    splitter = Splitter()
    split_paths = splitter.split(
        str(input_path),
        cue_path_or_timestamps=str(cue_path),
        output_dir=str(out_dir),
        format=format,
    )
    console.print(f"  Split into {len(split_paths)} files")

    tag_result = tag_tracks(
        track_dir=str(out_dir),
        cue_path=str(cue_path),
        beets_config=beets_config,
        use_beets=use_beets,
        beets_mode=beets_mode,
    )
    if tag_result.success:
        console.print(f"  [green]Tagged {len(tag_result.tagged_files)} files.[/green]")
    else:
        console.print(f"  [yellow]Tagging: {len(tag_result.warnings)} warnings[/yellow]")

    if cleanup_pregap_flag:
        console.print("[bold]Post-split cleanup...[/bold]")
        try:
            cleanup_actions = cleanup_tracks(
                track_dir=str(out_dir),
                min_duration=min_track_duration,
                remove_pregap=True,
                dry_run=False,
            )
            console.print(f"  Removed/renamed {len(cleanup_actions)} files")
        except Exception as exc:
            logger.error("Post-split cleanup failed: %s", exc)
            console.print(f"[yellow]Cleanup failed: {exc}[/yellow]")

    console.print(f"\n[bold green]✓ Pipeline complete. Output in {out_dir}[/bold green]")


@app.command()
def tui() -> None:
    """Launch the interactive Textual TUI."""
    try:
        from cue_finder.tui.app import launch_tui
        launch_tui()
    except ImportError:
        console.print("[yellow]TUI module not available. Install textual to use the TUI.[/yellow]")
        raise typer.Exit(EXIT_MISSING_DEPS)


def main() -> None:
    """Entry point for the cue-finder CLI.

    Auto-detects TTY: if running in a terminal with no subcommand, launches TUI.
    """
    if len(sys.argv) == 1 and sys.stdin.isatty():
        sys.argv.append("tui")
    app()


if __name__ == "__main__":
    main()
