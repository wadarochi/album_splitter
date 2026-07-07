"""Tests for post-split cleanup module."""

import numpy as np
import pytest
import soundfile

from cue_finder.core.cleanup import cleanup_tracks


def _write_flac(path, duration, samplerate=22050):
    samples = int(duration * samplerate)
    data = np.zeros(samples, dtype=np.float32)
    soundfile.write(str(path), data, samplerate)


class TestCleanupTracks:
    def test_removes_pregap_and_renumbers(self, tmp_path):
        _write_flac(tmp_path / "00 - pregap.flac", 5.0)
        _write_flac(tmp_path / "01 - First.flac", 30.0)
        _write_flac(tmp_path / "02 - Second.flac", 30.0)

        actions = cleanup_tracks(tmp_path, min_duration=0.0)

        assert not (tmp_path / "00 - pregap.flac").exists()
        assert (tmp_path / "01 - First.flac").exists()
        assert (tmp_path / "02 - Second.flac").exists()
        assert len(actions) == 1
        assert actions[0].reason.startswith("pregap")

    def test_removes_short_tracks(self, tmp_path):
        _write_flac(tmp_path / "01 - Long.flac", 30.0)
        _write_flac(tmp_path / "02 - Short.flac", 3.0)
        _write_flac(tmp_path / "03 - Another.flac", 30.0)

        actions = cleanup_tracks(tmp_path, min_duration=10.0)

        assert (tmp_path / "01 - Long.flac").exists()
        assert not (tmp_path / "02 - Short.flac").exists()
        assert (tmp_path / "02 - Another.flac").exists()
        removed = [a for a in actions if a.new_path is None]
        assert len(removed) == 1
        assert "short" in removed[0].reason

    def test_renumbers_after_removals(self, tmp_path):
        _write_flac(tmp_path / "00 - pregap.flac", 5.0)
        _write_flac(tmp_path / "01 - Alpha.flac", 30.0)
        _write_flac(tmp_path / "02 - Beta.flac", 3.0)
        _write_flac(tmp_path / "03 - Gamma.flac", 30.0)

        cleanup_tracks(tmp_path, min_duration=10.0)

        assert not (tmp_path / "00 - pregap.flac").exists()
        assert not (tmp_path / "02 - Beta.flac").exists()
        assert (tmp_path / "01 - Alpha.flac").exists()
        assert (tmp_path / "02 - Gamma.flac").exists()

    def test_dry_run_does_not_change_files(self, tmp_path):
        _write_flac(tmp_path / "00 - silence.flac", 5.0)
        _write_flac(tmp_path / "01 - Track.flac", 30.0)

        actions = cleanup_tracks(tmp_path, min_duration=10.0, dry_run=True)

        assert (tmp_path / "00 - silence.flac").exists()
        assert (tmp_path / "01 - Track.flac").exists()
        assert len(actions) == 1

    def test_keeps_pregap_when_disabled(self, tmp_path):
        _write_flac(tmp_path / "00 - pregap.flac", 5.0)
        _write_flac(tmp_path / "01 - Track.flac", 30.0)

        cleanup_tracks(tmp_path, min_duration=0.0, remove_pregap=False)

        assert (tmp_path / "00 - pregap.flac").exists()
        assert (tmp_path / "01 - Track.flac").exists()

    def test_ignores_non_track_files(self, tmp_path):
        _write_flac(tmp_path / "01 - Track.flac", 30.0)
        (tmp_path / "album.cue").write_text("CUE\n")
        (tmp_path / "cover.jpg").write_text("image")

        actions = cleanup_tracks(tmp_path, min_duration=10.0)

        assert (tmp_path / "01 - Track.flac").exists()
        assert (tmp_path / "album.cue").exists()
        assert (tmp_path / "cover.jpg").exists()
        assert not actions

    def test_preserves_original_order(self, tmp_path):
        _write_flac(tmp_path / "03 - Third.flac", 10.0)
        _write_flac(tmp_path / "01 - First.flac", 10.0)
        _write_flac(tmp_path / "02 - Second.flac", 10.0)

        cleanup_tracks(tmp_path, min_duration=0.0)

        assert (tmp_path / "01 - First.flac").exists()
        assert (tmp_path / "02 - Second.flac").exists()
        assert (tmp_path / "03 - Third.flac").exists()

    def test_no_tracks_directory(self, tmp_path):
        with pytest.raises(NotADirectoryError):
            cleanup_tracks(tmp_path / "missing")
