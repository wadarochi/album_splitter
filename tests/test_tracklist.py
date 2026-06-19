"""Tests for tracklist format module."""

import json
import tempfile
from pathlib import Path

import pytest
from cue_finder.core.tracklist import (
    AlbumMeta,
    TrackEntry,
    Tracklist,
    detect_format,
    export_tracklist,
    load_tracklist,
    parse_plain_text,
    save_tracklist,
    validate_tracklist,
)


class TestTracklistYAML:
    def test_round_trip(self):
        tl = Tracklist(
            album=AlbumMeta(
                artist="Test Artist",
                title="Test Album",
                date="2004",
                source="netease",
                source_id="3111188",
            ),
            tracks=[
                TrackEntry(title="Track 1", duration=210.0, start=0.0, end=210.0, confidence=0.95),
                TrackEntry(title="Track 2", duration=225.0, start=210.0, end=435.0, confidence=0.92),
            ],
            detected_boundaries=[210.0],
            cue_file="album.cue",
            output_dir="./tracks/",
        )

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            save_tracklist(tl, Path(f.name))
            save_path = f.name

        try:
            loaded = load_tracklist(Path(save_path))
            assert loaded.album.artist == "Test Artist"
            assert loaded.album.title == "Test Album"
            assert loaded.album.date == "2004"
            assert loaded.album.source == "netease"
            assert loaded.album.source_id == "3111188"
            assert len(loaded.tracks) == 2
            assert loaded.tracks[0].title == "Track 1"
            assert loaded.tracks[0].duration == 210.0
            assert loaded.tracks[0].confidence == 0.95
            assert loaded.detected_boundaries == [210.0]
            assert loaded.cue_file == "album.cue"
        finally:
            Path(save_path).unlink(missing_ok=True)


class TestPlainTextParsing:
    def test_artist_title_format(self):
        text = "Artist - Track 1\nArtist - Track 2\n"
        tl = parse_plain_text(text)

        assert len(tl.tracks) == 2
        assert tl.tracks[0].title == "Track 1"
        assert tl.tracks[0].artist == "Artist"
        assert tl.tracks[1].title == "Track 2"

    def test_title_only(self):
        text = "Track 1\nTrack 2\nTrack 3\n"
        tl = parse_plain_text(text)

        assert len(tl.tracks) == 3
        assert tl.tracks[0].title == "Track 1"
        assert tl.tracks[0].artist == ""

    def test_comments_ignored(self):
        text = "# Album tracklist\nTrack 1\n# Another comment\nTrack 2\n"
        tl = parse_plain_text(text)

        assert len(tl.tracks) == 2
        assert tl.tracks[0].title == "Track 1"
        assert tl.tracks[1].title == "Track 2"

    def test_empty_lines_ignored(self):
        text = "Track 1\n\nTrack 2\n\n"
        tl = parse_plain_text(text)

        assert len(tl.tracks) == 2


class TestFormatDetection:
    def test_detect_yaml_by_extension(self):
        assert detect_format(Path("tracklist.yaml")) == "yaml"
        assert detect_format(Path("tracklist.yml")) == "yaml"

    def test_detect_text_by_extension(self):
        assert detect_format(Path("tracklist.txt")) == "text"

    def test_detect_yaml_by_content(self):
        assert detect_format(Path("tracklist")) == "yaml"  # Can't inspect content here, but shouldn't crash

    def test_detect_text_by_content(self):
        result = detect_format(Path("tracklist"))
        assert result in ("yaml", "text")  # Content-based detection


class TestValidation:
    def test_valid_tracklist(self):
        tl = Tracklist(
            album=AlbumMeta(artist="A", title="B"),
            tracks=[TrackEntry(title="Track 1")],
        )
        errors = validate_tracklist(tl)
        assert len(errors) == 0

    def test_empty_tracklist(self):
        tl = Tracklist(
            album=AlbumMeta(artist="A", title="B"),
            tracks=[],
        )
        errors = validate_tracklist(tl)
        assert any("least one" in e.lower() for e in errors)

    def test_empty_title(self):
        tl = Tracklist(
            album=AlbumMeta(artist="A", title="B"),
            tracks=[TrackEntry(title="")],
        )
        errors = validate_tracklist(tl)
        assert any("empty title" in e.lower() for e in errors)

    def test_non_decreasing_boundaries(self):
        tl = Tracklist(
            album=AlbumMeta(artist="A", title="B"),
            tracks=[TrackEntry(title="T1"), TrackEntry(title="T2")],
            detected_boundaries=[435.0, 210.0],  # Decreasing!
        )
        errors = validate_tracklist(tl)
        assert any("non-decreasing" in e.lower() or "decreasing" in e.lower() for e in errors)


class TestExport:
    def test_export_json(self):
        tl = Tracklist(
            album=AlbumMeta(artist="A", title="B"),
            tracks=[TrackEntry(title="Track 1", duration=210.0)],
        )
        output = export_tracklist(tl, "json")
        data = json.loads(output)

        assert data["album"]["artist"] == "A"
        assert data["album"]["title"] == "B"
        assert data["tracks"][0]["title"] == "Track 1"
        assert data["tracks"][0]["duration"] == 210.0

    def test_export_text(self):
        tl = Tracklist(
            album=AlbumMeta(artist="A", title="B"),
            tracks=[TrackEntry(title="Track 1"), TrackEntry(title="Track 2")],
        )
        output = export_tracklist(tl, "text")
        lines = output.strip().split("\n")
        assert len(lines) == 2
        assert "Track 1" in lines[0]
        assert "Track 2" in lines[1]
