"""Textual TUI for cue-finder — interactive album search, track editing, CUE preview, and pipeline execution."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ProgressBar,
    RichLog,
    Static,
)


class FilePickerScreen(ModalScreen[str | None]):
    """Modal screen for selecting an audio file path."""

    DEFAULT_CSS = """
    FilePickerScreen {
        align: center middle;
    }
    FilePickerScreen > Vertical {
        width: 60;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Enter the path to an audio file (FLAC, WAV, or APE):")
            yield Input(placeholder="e.g. F:\\music\\album.flac", id="file_path_input")
            with Horizontal():
                yield Button("OK", variant="primary", id="ok_btn")
                yield Button("Cancel", variant="default", id="cancel_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "ok_btn":
            path = self.query_one("#file_path_input", Input).value.strip()
            if path:
                self.dismiss(path)
            else:
                self.dismiss(None)
        else:
            self.dismiss(None)


class CueFinderApp(App[None]):
    """Interactive TUI for cue-finder."""

    CSS = """
    #search_container {
        height: auto;
        margin: 1 0;
    }

    #search_input {
        dock: left;
        width: 1fr;
    }

    #search_button, #search_source {
        dock: right;
        margin-left: 1;
    }

    #main_area {
        height: 1fr;
    }

    #results_view {
        width: 50%;
        border: solid $primary;
        margin-right: 1;
    }

    #track_preview {
        width: 50%;
        border: solid $primary;
    }

    #cue_preview_container {
        height: 12;
        border: solid $primary;
        margin-top: 1;
    }

    #cue_preview {
        height: 100%;
    }

    #progress_container {
        height: auto;
        margin-top: 1;
        display: none;
    }

    #step_label {
        text-style: bold;
        padding-bottom: 1;
    }

    DataTable {
        height: 100%;
    }

    .hidden {
        display: none;
    }
    """

    BINDINGS: list[Binding] = [
        Binding("ctrl+s", "focus_search", "Search", priority=True),
        Binding("ctrl+r", "run_pipeline", "Run Pipeline", priority=True),
        Binding("ctrl+q", "quit", "Quit", priority=True),
        Binding("ctrl+o", "open_file", "Open File", priority=True),
        Binding("enter", "confirm_selection", "Select", priority=False),
    ]

    def __init__(self, audio_path: str | None = None) -> None:
        super().__init__()
        self._audio_path: str | None = audio_path
        self._boundaries: list[float] = []
        self._album_info: Optional["AlbumInfo"] = None
        self._sample_rate: int = 44100
        self._total_duration: float = 0.0

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Horizontal(
                Input(placeholder="Search album...", id="search_input"),
                Button("Search", variant="primary", id="search_button"),
            ),
            id="search_container",
        )
        yield Container(
            Vertical(Label("Search Results"), DataTable(id="results_table"), id="results_view"),
            Vertical(Label("Track List"), DataTable(id="track_table"), id="track_preview"),
            id="main_area",
        )
        yield Container(
            Label("CUE Preview"),
            RichLog(id="cue_preview", highlight=True, markup=True),
            id="cue_preview_container",
        )
        yield Container(
            Label("", id="step_label"),
            ProgressBar(total=100, show_eta=False, id="pipeline_progress"),
            id="progress_container",
        )
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the TUI on mount."""
        results_table = self.query_one("#results_table", DataTable)
        results_table.add_columns("Album", "Artist", "Year", "Tracks", "Source")
        results_table.cursor_type = "row"

        track_table = self.query_one("#track_table", DataTable)
        track_table.add_columns("#", "Title", "Start", "End", "Duration", "Confidence")
        track_table.cursor_type = "row"

    # --- Actions ---

    def action_focus_search(self) -> None:
        self.query_one("#search_input", Input).focus()

    def action_open_file(self) -> None:
        self.push_screen(FilePickerScreen(), self._on_file_selected)

    def _on_file_selected(self, path: str | None) -> None:
        if path:
            self._audio_path = path
            self._run_detection()

    def action_confirm_selection(self) -> None:
        """Handle Enter key — select from results table or focus search."""
        focused = self.focused
        if focused and focused.id == "results_table":
            self._on_result_selected()
        else:
            self.action_focus_search()

    def action_run_pipeline(self) -> None:
        if not self._audio_path:
            self.notify("No audio file selected. Press Ctrl+O to open one.", severity="warning")
            return
        self._run_full_pipeline()

    # --- Button handlers ---

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "search_button":
            self._run_search()

    # --- Search ---

    def _run_search(self) -> None:
        query = self.query_one("#search_input", Input).value.strip()
        if not query:
            self.notify("Enter a search query.", severity="warning")
            return

        try:
            from cue_finder.core.search import search_album, AlbumInfo

            results = search_album(query)
        except Exception as exc:
            self.notify(f"Search failed: {exc}", severity="error")
            return

        table = self.query_one("#results_table", DataTable)
        table.clear()
        if not results:
            self.notify("No results found.", severity="information")
            return

        for album in results:
            table.add_row(
                album.title,
                album.artist,
                album.date or "—",
                str(len(album.tracks)),
                album.source,
            )

        self.notify(f"Found {len(results)} results.", title="Search")

    def _on_result_selected(self) -> None:
        table = self.query_one("#results_table", DataTable)
        try:
            row_key = table.coordinate_to_cell_key(table.cursor_coordinate)
            row = table.get_row(row_key)
        except Exception:
            return

        from cue_finder.core.search import search_album, AlbumInfo

        query = self.query_one("#search_input", Input).value.strip()
        try:
            results = search_album(query)
            if results and row:
                idx = min(row.index, len(results) - 1)
                self._album_info = results[idx]
                self._populate_track_list()
        except Exception:
            pass

    def _populate_track_list(self) -> None:
        if not self._album_info:
            return

        track_table = self.query_one("#track_table", DataTable)
        track_table.clear()

        total_dur = self._total_duration or 1.0
        track_count = len(self._album_info.tracks)
        dur_per_track = total_dur / track_count if track_count else 0.0

        for i, track in enumerate(self._album_info.tracks):
            start = i * dur_per_track
            track_table.add_row(
                str(i + 1),
                track.title,
                f"{start:.1f}s",
                f"{(i + 1) * dur_per_track:.1f}s",
                f"{track.duration_sec or dur_per_track:.1f}s",
                "—",
            )

        self._update_cue_preview()

    # --- Detection ---

    def _run_detection(self) -> None:
        if not self._audio_path:
            return

        import soundfile
        from cue_finder.core.silence import SilenceDetector

        try:
            detector = SilenceDetector()
            self._boundaries = detector.detect_boundaries(self._audio_path)

            with soundfile.SoundFile(self._audio_path) as sf:
                self._sample_rate = sf.samplerate
                self._total_duration = sf.frames / sf.samplerate

            self.notify(
                f"Detected {len(self._boundaries)} boundaries "
                f"({len(self._boundaries) + 1} tracks)",
                title="Detection",
            )
        except Exception as exc:
            self.notify(f"Detection failed: {exc}", severity="error")

    # --- CUE Preview ---

    def _update_cue_preview(self) -> None:
        from cue_finder.core.cue import CueTrack, generate_cue, seconds_to_msf

        if not self._album_info or not self._audio_path:
            return

        tracks = [
            CueTrack(
                track_number=i + 1,
                title=t.title,
                performer=t.artist or self._album_info.artist,
                index01=seconds_to_msf(i * (self._total_duration / max(len(self._album_info.tracks), 1)), self._sample_rate),
                start_seconds=i * (self._total_duration / max(len(self._album_info.tracks), 1)),
            )
            for i, t in enumerate(self._album_info.tracks)
        ]

        cue_text = generate_cue(
            album_artist=self._album_info.artist,
            album_title=self._album_info.title,
            audio_filename=Path(self._audio_path).name,
            tracks=tracks,
        )

        cue_log = self.query_one("#cue_preview", RichLog)
        cue_log.clear()
        cue_log.write(cue_text)

    # --- Pipeline ---

    def _run_full_pipeline(self) -> None:
        from cue_finder.core.cue import CueTrack, generate_cue, seconds_to_msf, write_cue
        from cue_finder.core.split import Splitter

        progress_bar = self.query_one("#pipeline_progress", ProgressBar)
        step_label = self.query_one("#step_label", Label)
        progress_container = self.query_one("#progress_container")
        progress_container.styles.display = "block"

        try:
            out_dir = Path(self._audio_path).parent / "split_output"
            out_dir.mkdir(parents=True, exist_ok=True)

            # Step 1: Detect (already done via _run_detection, re-run if needed)
            step_label.update("Step 1/4: Detecting boundaries...")
            progress_bar.update(progress=10)
            if not self._boundaries:
                self._run_detection()
            progress_bar.update(progress=25)

            # Step 2: Generate CUE
            step_label.update("Step 2/4: Generating CUE sheet...")
            progress_bar.update(progress=35)

            album = self._album_info
            if not album:
                progress_container.styles.display = "none"
                self.notify("Search for an album first.", severity="warning")
                return

            cue_tracks = [
                CueTrack(
                    track_number=i + 1,
                    title=t.title,
                    performer=t.artist or album.artist,
                    index01=seconds_to_msf(
                        i * (self._total_duration / max(len(album.tracks), 1)),
                        self._sample_rate,
                    ),
                    start_seconds=i * (self._total_duration / max(len(album.tracks), 1)),
                )
                for i, t in enumerate(album.tracks)
            ]

            audio_name = Path(self._audio_path).name
            cue_text = generate_cue(
                album_artist=album.artist,
                album_title=album.title,
                audio_filename=audio_name,
                tracks=cue_tracks,
            )
            cue_path = out_dir / f"{Path(self._audio_path).stem}.cue"
            write_cue(cue_text, str(cue_path))
            progress_bar.update(progress=50)

            # Step 3: Split
            step_label.update("Step 3/4: Splitting audio...")
            splitter = Splitter()
            splitter.split(str(self._audio_path), str(cue_path), str(out_dir))
            progress_bar.update(progress=75)

            # Step 4: Tag
            step_label.update("Step 4/4: Tagging tracks...")
            from cue_finder.core.tag import tag_tracks

            result = tag_tracks(str(out_dir), str(cue_path), use_beets=False)
            progress_bar.update(progress=100)

            progress_container.styles.display = "none"

            if result.success:
                self.notify(
                    f"Pipeline complete! {len(result.tagged_files)} files in {out_dir}",
                    title="Success",
                )
            else:
                self.notify(
                    f"Done with warnings ({len(result.warnings)}). Output in {out_dir}",
                    title="Warning",
                )

        except Exception as exc:
            progress_container.styles.display = "none"
            self.notify(f"Pipeline failed: {exc}", severity="error")


def launch_tui(audio_path: str | None = None) -> None:
    """Launch the cue-finder Textual TUI."""
    app = CueFinderApp(audio_path=audio_path)
    app.run()
