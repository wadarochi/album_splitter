"""Tests for track matching module."""

import pytest
from cue_finder.core.match import TrackMatcher, TrackMatch


class TestTrackMatcher:
    def test_perfect_match_n_equals_m(self):
        matcher = TrackMatcher(tolerance=3.0)
        boundaries = [210.0, 435.0]  # 3 segments
        durations = [210.0, 225.0, 165.0]  # 3 tracks
        titles = ["Track 1", "Track 2", "Track 3"]
        artists = ["Artist"] * 3

        matches = matcher.match(
            boundaries, durations, titles, artists, total_duration=600.0
        )

        assert len(matches) == 3
        for m in matches:
            assert m.confidence >= 0.90

    def test_duration_mismatch_within_tolerance(self):
        matcher = TrackMatcher(tolerance=5.0)
        boundaries = [208.0, 437.0]  # Slightly off
        durations = [210.0, 225.0, 165.0]
        titles = ["T1", "T2", "T3"]
        artists = ["A"] * 3

        matches = matcher.match(
            boundaries, durations, titles, artists, total_duration=600.0
        )

        assert len(matches) == 3
        # Should still match but with slightly lower confidence
        assert all(m.confidence > 0.7 for m in matches)

    def test_more_boundaries_than_tracks(self):
        matcher = TrackMatcher(tolerance=3.0)
        boundaries = [210.0, 300.0, 435.0]  # 4 segments (extra)
        durations = [210.0, 225.0, 165.0]  # 3 tracks
        titles = ["T1", "T2", "T3"]
        artists = ["A"] * 3

        matches = matcher.match(
            boundaries, durations, titles, artists, total_duration=600.0
        )

        # Should produce matches with extra_segment flag
        assert len(matches) == 3
        assert any("extra_segment" in m.flags for m in matches)

    def test_fewer_boundaries_than_tracks(self):
        matcher = TrackMatcher(tolerance=3.0)
        boundaries = [210.0]  # 2 segments
        durations = [210.0, 225.0, 165.0]  # 3 tracks
        titles = ["T1", "T2", "T3"]
        artists = ["A"] * 3

        matches = matcher.match(
            boundaries, durations, titles, artists, total_duration=600.0
        )

        assert len(matches) == 3
        assert any("missing_track" in m.flags for m in matches)

    def test_no_boundaries_single_track_guess(self):
        matcher = TrackMatcher()
        boundaries: list[float] = []
        durations = [210.0, 225.0, 165.0]
        titles = ["T1", "T2", "T3"]
        artists = ["A"] * 3

        matches = matcher.match(
            boundaries, durations, titles, artists, total_duration=600.0
        )

        assert len(matches) == 3
        assert all("no_boundaries" in m.flags for m in matches)

    def test_titles_and_artists_assigned(self):
        matcher = TrackMatcher()
        boundaries = [210.0, 435.0]
        durations = [210.0, 225.0, 165.0]
        titles = ["Alpha", "Beta", "Gamma"]
        artists = ["ArtistX", "ArtistX", "ArtistY"]

        matches = matcher.match(
            boundaries, durations, titles, artists, total_duration=600.0
        )

        assert matches[0].title == "Alpha"
        assert matches[0].artist == "ArtistX"
        assert matches[2].title == "Gamma"
        assert matches[2].artist == "ArtistY"

    def test_greedy_fallback_used(self):
        # Very tight tolerance forces DTW to produce low confidence
        matcher = TrackMatcher(tolerance=0.1)
        boundaries = [210.0, 435.0]
        durations = [210.0, 225.0, 165.0]
        titles = ["T1", "T2", "T3"]
        artists = ["A"] * 3

        matches = matcher.match(
            boundaries, durations, titles, artists, total_duration=600.0
        )

        # Should produce matches (greedy fallback kicks in)
        assert len(matches) == 3

    def test_filter_false_positives(self):
        matcher = TrackMatcher(tolerance=3.0)
        boundaries = [210.0, 300.0, 435.0]  # 300 is a false positive
        expected = [210.0, 435.0]

        filtered = matcher.filter_false_positives(boundaries, expected)

        assert len(filtered) == 2
        assert 210.0 in filtered
        assert 435.0 in filtered
        assert 300.0 not in filtered

    def test_detect_htoa(self):
        matcher = TrackMatcher()
        boundaries = [30.0, 240.0]  # 30s before first track

        assert matcher.detect_htoa(boundaries, total_duration=600.0, min_htoa_sec=10.0)

    def test_no_htoa_short_gap(self):
        matcher = TrackMatcher()
        boundaries = [5.0, 240.0]  # Only 5s before first track

        assert not matcher.detect_htoa(
            boundaries, total_duration=600.0, min_htoa_sec=10.0
        )

    def test_no_htoa_no_boundaries(self):
        matcher = TrackMatcher()
        boundaries: list[float] = []

        assert not matcher.detect_htoa(
            boundaries, total_duration=600.0, min_htoa_sec=10.0
        )
