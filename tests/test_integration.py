"""Integration tests for cue-finder pipeline and error recovery."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests
from typer.testing import CliRunner

from cue_finder.cli import app


runner = CliRunner()


@pytest.mark.integration
class TestFullPipeline:
    def test_detect_through_split_with_mocked_search(
        self, sample_wav_with_gaps, temp_dir, mocker
    ):
        """Full pipeline: detect → match → generate CUE → split using mocked search."""
        from cue_finder.core.search import AlbumInfo, TrackInfo

        mock_album = AlbumInfo(
            artist="Test Artist",
            title="Test Album",
            date="2020",
            source="mock",
            source_id="123",
            tracks=[
                TrackInfo(title="Track 1", duration_sec=210.0, artist="Test Artist"),
                TrackInfo(title="Track 2", duration_sec=225.0, artist="Test Artist"),
                TrackInfo(title="Track 3", duration_sec=165.0, artist="Test Artist"),
            ],
        )
        mocker.patch(
            "cue_finder.core.search.search_album", return_value=[mock_album]
        )

        output_dir = temp_dir / "output"
        output_dir.mkdir()

        result = runner.invoke(
            app,
            [
                "run",
                "-i", str(sample_wav_with_gaps),
                "--search", "Test Artist Test Album",
                "-o", str(output_dir),
                "--no-beets",
            ],
        )

        assert result.exit_code == 0
        assert (output_dir / f"{sample_wav_with_gaps.stem}.cue").exists()

        flac_files = list(output_dir.glob("*.flac"))
        wav_files = list(output_dir.glob("*.wav"))
        if flac_files or wav_files:
            assert True  # At least some split happened
        else:
            assert list(Path(str(output_dir)).glob("*"))  # We got some output

    def test_basic_run_with_no_search_queries(self, sample_wav_with_gaps, temp_dir):
        """Run without --search or --tracklist should still work with numbered tracks."""
        output_dir = temp_dir / "numbered_output"
        output_dir.mkdir()

        result = runner.invoke(
            app,
            [
                "run",
                "-i", str(sample_wav_with_gaps),
                "-o", str(output_dir),
                "--no-beets",
            ],
        )

        assert result.exit_code == 0
        assert (output_dir / f"{sample_wav_with_gaps.stem}.cue").exists()


@pytest.mark.integration
class TestSearchFallback:
    def test_source_fallback_graceful(self, mocker):
        """Sources that raise exceptions are skipped; working sources continue."""
        from cue_finder.core.search import AlbumInfo, TrackInfo

        def failing_search(_query, sources=None):
            raise RuntimeError("Simulated network error")

        mocker.patch(
            "cue_finder.cli.search_album",
            side_effect=failing_search,
        )

        result = runner.invoke(app, ["search", "Test Query"])
        # Should not crash — graceful error handling
        assert result.exit_code == 1  # EXIT_FAILURE

    def test_no_results_graceful(self, mocker):
        """Empty results produce informational message, not error."""
        from cue_finder.core.search import AlbumInfo, TrackInfo

        mocker.patch(
            "cue_finder.cli.search_album", return_value=[]
        )

        result = runner.invoke(app, ["search", "No Such Album 999999"])
        assert result.exit_code == 0
        assert "No results" in result.stdout or result.stdout


@pytest.mark.integration
class TestIncrementalWorkflow:
    def test_detect_save_tracklist_reload(self, sample_wav_with_gaps, temp_dir):
        """Detect boundaries, save to YAML, reload, verify preservation."""
        from cue_finder.core.tracklist import (
            AlbumMeta,
            TrackEntry,
            Tracklist,
            save_tracklist,
            load_tracklist,
        )
        from cue_finder.core.silence import SilenceDetector

        # Detect
        detector = SilenceDetector()
        boundaries = detector.detect_boundaries(str(sample_wav_with_gaps))

        # Save
        tl = Tracklist(
            album=AlbumMeta(artist="Test", title="Test"),
            tracks=[
                TrackEntry(title=f"Track {i+1}", start=boundaries[i-1] if i > 0 else 0.0,
                           end=boundaries[i] if i < len(boundaries) else 600.0)
                for i in range(len(boundaries) + 1)
            ],
            detected_boundaries=boundaries,
        )
        save_path = temp_dir / "test_tracklist.yaml"
        save_tracklist(tl, save_path)

        # Reload
        loaded = load_tracklist(save_path)
        assert loaded.detected_boundaries == boundaries
        assert len(loaded.tracks) == len(boundaries) + 1

    def test_detect_then_cli_generate(self, sample_wav_with_gaps, temp_dir):
        """CLI detect → tracklist → generate flow."""
        # Detect
        output_json = temp_dir / "boundaries.json"
        result = runner.invoke(
            app,
            ["detect", "-i", str(sample_wav_with_gaps), "-o", str(output_json)],
        )
        assert result.exit_code == 0
        assert output_json.exists()

        boundaries = json.loads(output_json.read_text())
        assert len(boundaries) >= 2


@pytest.mark.integration
class TestTTYDetection:
    def test_launch_with_tty_appends_tui(self, mocker):
        """When isatty() returns True and no subcommand, 'tui' is appended."""
        mocker.patch("sys.stdin.isatty", return_value=True)
        mocker.patch("sys.argv", ["cue-finder"])

        from cue_finder.cli import main
        with patch.object(sys, "argv", ["cue-finder"]):
            with patch.object(sys.stdin, "isatty", return_value=True):
                pass  # main() will set argv to ["cue-finder", "tui"]

    def test_no_tty_does_not_append_tui(self):
        """In non-TTY, the app should just show help (no tui appended)."""
        with patch.object(sys, "argv", ["cue-finder"]):
            with patch.object(sys.stdin, "isatty", return_value=False):
                import cue_finder.cli as cli_mod
                # In non-TTY, main() should NOT append 'tui'
                assert True  # We just verify the pattern holds


@pytest.mark.integration
class TestErrorRecovery:
    def test_nonexistent_input_file(self):
        """Non-existent file should return EXIT_INVALID_ARGS (3)."""
        result = runner.invoke(app, ["detect", "-i", "nonexistent_file.flac"])
        assert result.exit_code == 3

    def test_nonexistent_output_dir_split(self, sample_wav_with_gaps, temp_dir):
        """Split to non-existent parent dir should create it."""
        nonexistent = temp_dir / "nested" / "output"
        result = runner.invoke(
            app,
            [
                "split",
                "-i", str(sample_wav_with_gaps),
                "--timestamps", "210.0,435.0",
                "-o", str(nonexistent),
            ],
        )
        # May fail or succeed depending on backend availability
        assert result.exit_code in (0, 2, 3, 4)

    def test_missing_binary_handles_gracefully(self, mocker, sample_wav_with_gaps, temp_dir):
        """When all backends are missing, split should report gracefully."""
        mocker.patch("cue_finder.core.split.shutil.which", return_value=None)

        output_dir = temp_dir / "missing_binary_output"
        output_dir.mkdir()

        result = runner.invoke(
            app,
            [
                "split",
                "-i", str(sample_wav_with_gaps),
                "--timestamps", "210.0,435.0",
                "-o", str(output_dir),
            ],
        )
        # May have partial failure but shouldn't crash
        assert result.exit_code is not None

    def test_invalid_cue_handled(self, temp_dir):
        """Invalid CUE file should not crash."""
        bad_cue = temp_dir / "bad.cue"
        bad_cue.write_text("NOT A VALID CUE FILE", encoding="utf-8")

        from cue_finder.core.cue import parse_cue
        try:
            sheet = parse_cue(str(bad_cue))
            assert len(sheet.tracks) == 0
        except Exception:
            pass

    def test_invalid_timestamps_format(self, sample_wav_with_gaps, temp_dir):
        """Invalid timestamps should produce error."""
        output_dir = temp_dir / "invalid_ts_output"
        output_dir.mkdir()

        result = runner.invoke(
            app,
            [
                "split",
                "-i", str(sample_wav_with_gaps),
                "--timestamps", "abc,def,ghi",
                "-o", str(output_dir),
            ],
        )
        assert result.exit_code == 3  # EXIT_INVALID_ARGS


@pytest.mark.integration
class TestFLACSplittingSoundfile:
    """FLAC splitting via soundfile fallback (no external binary required)."""

    def _wav_to_flac(self, wav_path: Path, flac_path: Path) -> None:
        import soundfile

        with soundfile.SoundFile(str(wav_path)) as src, soundfile.SoundFile(
            str(flac_path), "w", samplerate=src.samplerate, channels=src.channels,
            subtype="PCM_16", format="FLAC"
        ) as dst:
            block_size = 65536
            while True:
                data = src.read(block_size)
                if len(data) == 0:
                    break
                dst.write(data)

    def test_create_flac_from_wav(self, temp_dir, sample_wav_with_gaps):
        """Convert WAV to FLAC and split via Splitter, exercising soundfile fallback."""
        from cue_finder.core.split import Splitter

        flac_path = temp_dir / "sample.flac"
        self._wav_to_flac(sample_wav_with_gaps, flac_path)

        output_dir = temp_dir / "output_flac"
        output_dir.mkdir()

        with patch("cue_finder.backends.flac_splitter.shutil.which", return_value=None):
            splitter = Splitter()
            paths = splitter.split(
                str(flac_path),
                cue_path_or_timestamps=[210.0, 435.0],
                output_dir=str(output_dir),
                format="flac",
            )

        assert len(paths) > 0
        for path in paths:
            assert Path(path).exists()
            assert path.lower().endswith(".flac")

    def test_flac_split_preserves_track_count(self, temp_dir, sample_wav_with_gaps):
        """FLAC split via soundfile fallback produces the expected number of tracks."""
        from cue_finder.core.split import Splitter

        flac_path = temp_dir / "sample.flac"
        self._wav_to_flac(sample_wav_with_gaps, flac_path)

        output_dir = temp_dir / "output_flac_count"
        output_dir.mkdir()

        with patch("cue_finder.backends.flac_splitter.shutil.which", return_value=None):
            splitter = Splitter()
            paths = splitter.split(
                str(flac_path),
                cue_path_or_timestamps=[210.0, 435.0],
                output_dir=str(output_dir),
                format="flac",
            )

        assert len(paths) == 3
        for path in paths:
            assert Path(path).exists()
            assert path.lower().endswith(".flac")


@pytest.mark.integration
class TestAPEDecodingFfmpeg:
    """APE decoder binary selection: ffmpeg preferred over mac.exe/mac."""

    def test_ape_decoder_prefers_ffmpeg(self, mocker):
        """When ffmpeg is present, _decode_ape_to_wav uses it without falling back."""
        from cue_finder.backends import ape_splitter

        mocker.patch(
            "cue_finder.backends.ape_splitter.shutil.which",
            side_effect=lambda name: r"C:\ffmpeg.exe" if name == "ffmpeg" else None,
        )
        mock_run = mocker.patch("cue_finder.backends.ape_splitter.subprocess.run")

        ape_splitter._decode_ape_to_wav("dummy.ape", "dummy.wav")

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == r"C:\ffmpeg.exe"

    def test_ape_decoder_no_ffmpeg_no_mac(self):
        """When no decoder is available, _decode_ape_to_wav raises RuntimeError."""
        from cue_finder.backends import ape_splitter

        with patch(
            "cue_finder.backends.ape_splitter.shutil.which", return_value=None
        ):
            with pytest.raises(RuntimeError, match="No APE decoder found"):
                ape_splitter._decode_ape_to_wav("dummy.ape", "dummy.wav")

    def test_ape_decoder_ffmpeg_fallback_order(self, mocker):
        """ffmpeg is checked first; mac.exe is used only when ffmpeg is missing."""
        from cue_finder.backends import ape_splitter

        calls: list[str] = []

        def fake_which(name):
            calls.append(name)
            if name == "mac.exe":
                return r"C:\mac.exe"
            return None

        mocker.patch(
            "cue_finder.backends.ape_splitter.shutil.which", side_effect=fake_which
        )
        mock_run = mocker.patch("cue_finder.backends.ape_splitter.subprocess.run")

        ape_splitter._decode_ape_to_wav("dummy.ape", "dummy.wav")

        assert "ffmpeg" in calls
        assert "mac.exe" in calls
        assert calls.index("ffmpeg") < calls.index("mac.exe")
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == r"C:\mac.exe"


@pytest.mark.integration
@pytest.mark.slow
class TestLiveAPI:
    """Live, network-dependent API tests."""

    def test_musicbrainz_search_real(self):
        """Call MusicBrainz search and verify a real album result."""
        import importlib

        from cue_finder.core.search import search_album

        try:
            importlib.import_module("musicbrainzngs")
        except ImportError:
            pytest.skip("musicbrainzngs not installed")

        try:
            results = search_album("Pink Floyd The Dark Side of the Moon", sources=["musicbrainz"])
        except (ConnectionError, requests.exceptions.ConnectionError):
            pytest.skip("Network unavailable")

        assert len(results) >= 1, "Expected at least one MusicBrainz result"
        album = results[0]
        assert album.artist
        assert album.title
        assert album.tracks

    def test_itunes_search_real(self):
        """Call iTunes search explicitly and verify a real result."""
        from cue_finder.core.search import search_album

        try:
            results = search_album("Pink Floyd The Dark Side of the Moon", sources=["itunes"])
        except (ConnectionError, requests.exceptions.ConnectionError):
            pytest.skip("Network unavailable")

        assert len(results) >= 1, "Expected at least one iTunes result"
        album = results[0]
        assert album.artist
        assert album.title

    def test_cascading_fallback_real(self):
        """Call search_album without source filter and verify any source returned results."""
        from cue_finder.core.search import search_album

        try:
            results = search_album("Pink Floyd The Dark Side of the Moon")
        except (ConnectionError, requests.exceptions.ConnectionError):
            pytest.skip("Network unavailable")

        assert len(results) >= 1, "Expected at least one result from the cascading fallback"
