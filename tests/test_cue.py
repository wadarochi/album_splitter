"""Tests for CUE generation module."""

import tempfile
from pathlib import Path

import pytest
from cue_finder.core.cue import (
    CueSheet,
    CueTrack,
    find_local_cue,
    generate_cue,
    msf_to_seconds,
    parse_cue,
    samples_to_msf,
    seconds_to_msf,
    validate_cue,
    write_cue,
)


class TestMSFConversion:
    def test_samples_to_msf_44100(self):
        # 210.0 seconds at 44100 Hz
        samples = int(210.0 * 44100)
        msf = samples_to_msf(samples, 44100)
        assert msf == "03:30:00"

    def test_samples_to_msf_48000(self):
        samples = int(210.0 * 48000)
        msf = samples_to_msf(samples, 48000)
        # 48000/75 = 640 samples per frame
        expected_frames = round(samples / 640)
        m = expected_frames // (60 * 75)
        s = (expected_frames % (60 * 75)) // 75
        f = expected_frames % 75
        expected = f"{m:02d}:{s:02d}:{f:02d}"
        assert msf == expected

    def test_seconds_to_msf(self):
        msf = seconds_to_msf(210.0, 44100)
        assert msf == "03:30:00"

    def test_seconds_to_msf_zero(self):
        msf = seconds_to_msf(0.0, 44100)
        assert msf == "00:00:00"

    def test_msf_to_seconds(self):
        seconds = msf_to_seconds("03:30:00")
        assert seconds == pytest.approx(210.0, rel=1e-3)

    def test_msf_to_seconds_with_frames(self):
        seconds = msf_to_seconds("03:30:37")
        expected = 210.0 + 37 / 75
        assert seconds == pytest.approx(expected, rel=1e-3)

    def test_msf_to_seconds_short_format(self):
        seconds = msf_to_seconds("03:30")
        assert seconds == pytest.approx(210.0, rel=1e-3)

    def test_round_trip(self):
        original = 210.5
        msf = seconds_to_msf(original, 44100)
        back = msf_to_seconds(msf)
        assert abs(back - original) < 1.0 / 75  # Within 1 frame


class TestCueGeneration:
    def test_generate_basic_cue(self):
        tracks = [
            CueTrack(1, "Track 1", "", "00:00:00", 0.0),
            CueTrack(2, "Track 2", "", "03:30:00", 210.0),
            CueTrack(3, "Track 3", "", "07:15:00", 435.0),
        ]
        cue_text = generate_cue(
            album_artist="Test Artist",
            album_title="Test Album",
            audio_filename="test.flac",
            matched_tracks=tracks,
        )

        assert 'PERFORMER "Test Artist"' in cue_text
        assert 'TITLE "Test Album"' in cue_text
        assert 'FILE "test.flac" WAVE' in cue_text
        assert 'TRACK 01 AUDIO' in cue_text
        assert 'TITLE "Track 1"' in cue_text
        assert 'INDEX 01 00:00:00' in cue_text
        assert 'TRACK 02 AUDIO' in cue_text
        assert 'INDEX 01 03:30:00' in cue_text

    def test_generate_cue_uses_basename(self):
        tracks = [CueTrack(1, "Track", "", "00:00:00", 0.0)]
        cue_text = generate_cue(
            album_artist="A",
            album_title="B",
            audio_filename=r"F:\music\album.flac",
            matched_tracks=tracks,
        )

        assert 'FILE "album.flac" WAVE' in cue_text

    def test_generate_cue_with_rem(self):
        tracks = [CueTrack(1, "Track", "", "00:00:00", 0.0)]
        cue_text = generate_cue(
            album_artist="A",
            album_title="B",
            audio_filename="test.flac",
            matched_tracks=tracks,
            rem_fields={"DATE": "2004", "GENRE": "Pop"},
        )

        assert 'REM DATE "2004"' in cue_text
        assert 'REM GENRE "Pop"' in cue_text


class TestCueParsing:
    def test_parse_valid_cue(self, temp_dir):
        import tempfile as _tmp
        cue_text = """PERFORMER "Test Artist"
TITLE "Test Album"
FILE "test.flac" WAVE
  TRACK 01 AUDIO
    TITLE "Track 1"
    INDEX 01 00:00:00
  TRACK 02 AUDIO
    TITLE "Track 2"
    INDEX 01 03:30:00
"""
        cue_path = temp_dir / "test.cue"
        cue_path.write_text(cue_text, encoding="utf-8-sig")
        sheet = parse_cue(cue_path)

        assert sheet.performer == "Test Artist"
        assert sheet.title == "Test Album"
        assert sheet.audio_filename == "test.flac"
        assert len(sheet.tracks) == 2
        assert sheet.tracks[0].title == "Track 1"
        assert sheet.tracks[0].index01 == "00:00:00"
        assert sheet.tracks[1].title == "Track 2"
        assert sheet.tracks[1].index01 == "03:30:00"

    def test_parse_cue_with_rem(self, temp_dir):
        cue_text = """REM DATE "2004"
REM GENRE "Pop"
PERFORMER "Artist"
TITLE "Album"
FILE "test.flac" WAVE
  TRACK 01 AUDIO
    TITLE "Track"
    INDEX 01 00:00:00
"""
        cue_path = temp_dir / "test_rem.cue"
        cue_path.write_text(cue_text, encoding="utf-8-sig")
        sheet = parse_cue(cue_path)

        assert sheet.rem_fields.get("DATE") == "2004"
        assert sheet.rem_fields.get("GENRE") == "Pop"


class TestCueValidation:
    def test_valid_cue(self):
        cue_text = """PERFORMER "Artist"
TITLE "Album"
FILE "test.flac" WAVE
  TRACK 01 AUDIO
    TITLE "T1"
    INDEX 01 00:00:00
  TRACK 02 AUDIO
    TITLE "T2"
    INDEX 01 03:30:00
"""
        errors = validate_cue(cue_text)
        assert len(errors) == 0

    def test_missing_index01(self):
        cue_text = """PERFORMER "Artist"
TITLE "Album"
FILE "test.flac" WAVE
  TRACK 01 AUDIO
    TITLE "T1"
  TRACK 02 AUDIO
    TITLE "T2"
    INDEX 01 03:30:00
"""
        errors = validate_cue(cue_text)
        assert any("INDEX 01" in e for e in errors)

    def test_non_sequential_tracks(self):
        cue_text = """PERFORMER "Artist"
TITLE "Album"
FILE "test.flac" WAVE
  TRACK 01 AUDIO
    TITLE "T1"
    INDEX 01 00:00:00
  TRACK 03 AUDIO
    TITLE "T3"
    INDEX 01 03:30:00
"""
        errors = validate_cue(cue_text)
        assert any("sequential" in e.lower() for e in errors)

    def test_first_track_not_zero(self):
        cue_text = """PERFORMER "Artist"
TITLE "Album"
FILE "test.flac" WAVE
  TRACK 01 AUDIO
    TITLE "T1"
    INDEX 01 00:00:05
"""
        errors = validate_cue(cue_text)
        assert any("00:00:00" in e for e in errors)


class TestCueWriteRead:
    def test_write_and_read_roundtrip(self, temp_dir):
        tracks = [
            CueTrack(1, "Track 1", "", "00:00:00", 0.0),
            CueTrack(2, "Track 2", "", "03:30:00", 210.0),
        ]
        cue_text = generate_cue(
            album_artist="Test Artist",
            album_title="Test Album",
            audio_filename="output.flac",
            matched_tracks=tracks,
        )

        cue_path = temp_dir / "roundtrip.cue"
        cue_path.write_text(cue_text, encoding="utf-8-sig")

        sheet = parse_cue(cue_path)
        assert sheet.performer == "Test Artist"
        assert sheet.title == "Test Album"
        assert len(sheet.tracks) == 2


class TestMultiDisc:
    def test_generate_multidisc_cue(self):
        from cue_finder.core.cue import generate_cue_multidisc

        disc1_tracks = [
            CueTrack(1, "D1T1", "", "00:00:00", 0.0),
            CueTrack(2, "D1T2", "", "03:30:00", 210.0),
        ]
        disc2_tracks = [
            CueTrack(3, "D2T1", "", "00:00:00", 0.0),  # Track numbers continue
            CueTrack(4, "D2T2", "", "04:00:00", 240.0),
        ]

        discs = [
            {"audio_filename": "disc1.flac", "tracks": disc1_tracks, "album_artist": "Artist", "album_title": "Album (Disc 1)"},
            {"audio_filename": "disc2.flac", "tracks": disc2_tracks, "album_artist": "Artist", "album_title": "Album (Disc 2)"},
        ]

        cue_text = generate_cue_multidisc(discs)

        assert 'FILE "disc1.flac" WAVE' in cue_text
        assert 'FILE "disc2.flac" WAVE' in cue_text
        assert 'TRACK 01 AUDIO' in cue_text
        assert 'TRACK 02 AUDIO' in cue_text
        assert 'TRACK 03 AUDIO' in cue_text
        assert 'TRACK 04 AUDIO' in cue_text


class TestFindLocalCue:
    def test_finds_same_stem_cue(self, tmp_path):
        audio = tmp_path / "album.flac"
        cue = tmp_path / "album.cue"
        audio.write_text("audio")
        cue.write_text("CUE")

        found = find_local_cue(audio)
        assert found == cue

    def test_prefers_exact_stem_over_partial_match(self, tmp_path):
        audio = tmp_path / "album.flac"
        exact = tmp_path / "album.cue"
        partial = tmp_path / "album_backup.cue"
        audio.write_text("audio")
        exact.write_text("CUE")
        partial.write_text("CUE")

        found = find_local_cue(audio)
        assert found == exact

    def test_returns_none_when_no_cue(self, tmp_path):
        audio = tmp_path / "album.flac"
        audio.write_text("audio")

        assert find_local_cue(audio) is None
