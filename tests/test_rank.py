"""Tests for album candidate ranking module."""

from cue_finder.core.rank import AlbumScore, score_candidates
from cue_finder.core.search import AlbumInfo, TrackInfo


def _album(artist: str, title: str, source: str, source_id: str, durations: list[float]) -> AlbumInfo:
    return AlbumInfo(
        artist=artist,
        title=title,
        date=None,
        source=source,
        source_id=source_id,
        tracks=[TrackInfo(title=f"Track {i + 1}", duration_sec=d, artist=artist) for i, d in enumerate(durations)],
    )


class TestScoreCandidates:
    def test_prefers_count_and_duration_match_over_text(self):
        # NetEase returns a noisy text match with wrong durations/count
        noisy = _album("S.H.E", "Best of S.H.E", "netease", "1", [180.0, 180.0, 180.0])
        # MusicBrainz returns the right album structurally
        right = _album("S.H.E", "Encore", "musicbrainz", "2", [210.0, 225.0, 165.0])

        boundaries = [210.0, 435.0]
        total_duration = 600.0
        query = "S.H.E Encore"

        scored = score_candidates([noisy, right], boundaries, total_duration, query)

        assert scored[0].album.source_id == "2"
        assert scored[0].album.source == "musicbrainz"

    def test_text_tier_still_matters_when_structure_equal(self):
        a = _album("S.H.E", "Encore", "musicbrainz", "1", [210.0, 225.0, 165.0])
        b = _album("Frank Sinatra", "Encore", "musicbrainz", "2", [210.0, 225.0, 165.0])

        boundaries = [210.0, 435.0]
        total_duration = 600.0

        scored = score_candidates([b, a], boundaries, total_duration, "S.H.E Encore")

        assert scored[0].album.source_id == "1"

    def test_fingerprint_hit_boosts_candidate(self):
        a = _album("S.H.E", "Encore", "musicbrainz", "1", [210.0, 225.0, 165.0])
        b = _album("S.H.E", "Encore", "musicbrainz", "2", [210.0, 225.0, 165.0])

        boundaries = [210.0, 435.0]
        total_duration = 600.0

        scored = score_candidates(
            [a, b],
            boundaries,
            total_duration,
            "S.H.E Encore",
            fingerprint_release_ids={"1"},
        )

        assert scored[0].album.source_id == "1"
        assert scored[0].fingerprint_hit is True

    def test_duration_mismatch_flag_set(self):
        album = _album("S.H.E", "Encore", "musicbrainz", "1", [100.0, 100.0, 100.0])
        boundaries = [210.0, 435.0]
        total_duration = 600.0

        scored = score_candidates([album], boundaries, total_duration, "S.H.E Encore")

        assert "duration_mismatch" in scored[0].flags

    def test_track_count_mismatch_flag_set(self):
        album = _album("S.H.E", "Encore", "musicbrainz", "1", [210.0, 225.0, 165.0, 30.0])
        boundaries = [210.0, 435.0]
        total_duration = 600.0

        scored = score_candidates([album], boundaries, total_duration, "S.H.E Encore")

        assert scored[0].count_delta == 1
        assert "track_count_mismatch" in scored[0].flags

    def test_scores_sorted_descending(self):
        a = _album("S.H.E", "Best Of", "netease", "1", [180.0] * 3)
        b = _album("S.H.E", "Encore", "musicbrainz", "2", [210.0, 225.0, 165.0])
        c = _album("S.H.E", "Live", "itunes", "3", [100.0] * 3)

        boundaries = [210.0, 435.0]
        total_duration = 600.0

        scored = score_candidates([a, c, b], boundaries, total_duration, "S.H.E Encore")

        scores = [s.total_score for s in scored]
        assert scores == sorted(scores, reverse=True)


class TestAlbumScoreDisambiguationFields:
    def test_default_values(self):
        from cue_finder.core.rank import AlbumScore
        from cue_finder.core.search import AlbumInfo, TrackInfo
        
        album = AlbumInfo(
            artist="S.H.E",
            title="Play",
            date="2007",
            source="itunes",
            source_id="1",
            tracks=[TrackInfo(title="Track 1", duration_sec=200.0, artist="S.H.E")],
        )
        score = AlbumScore(
            album=album,
            text_tier=0,
            count_delta=0,
            duration_score=0.8,
            fingerprint_hit=False,
            source_weight=0.9,
            total_score=0.75,
        )
        assert score.year_match is False
        assert score.barcode_match is False
        assert score.catalog_match is False
        assert score.track_name_similarity == 0.0
        assert score.country_hint is None
        assert score.disambiguation is None

    def test_custom_values(self):
        from cue_finder.core.rank import AlbumScore
        from cue_finder.core.search import AlbumInfo, TrackInfo
        
        album = AlbumInfo(
            artist="S.H.E",
            title="Play",
            date="2007",
            source="itunes",
            source_id="1",
            tracks=[TrackInfo(title="Track 1", duration_sec=200.0, artist="S.H.E")],
        )
        score = AlbumScore(
            album=album,
            text_tier=0,
            count_delta=0,
            duration_score=0.8,
            fingerprint_hit=False,
            source_weight=0.9,
            total_score=0.75,
            year_match=True,
            barcode_match=True,
            country_hint="TW",
            disambiguation="Deluxe Edition",
        )
        assert score.year_match is True
        assert score.barcode_match is True
        assert score.country_hint == "TW"
        assert score.disambiguation == "Deluxe Edition"
