"""Tests for interactive candidate selection module."""

from cue_finder.core.interactive import (
    SelectionAborted,
    _format_duration,
    _format_flags,
    _score_style,
    _suggest_disc_ranges,
    create_disc_subset,
    parse_range,
    should_prompt,
    should_split_disc,
)
from cue_finder.core.rank import AlbumScore
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


def _score(
    album: AlbumInfo,
    total_score: float = 0.5,
    text_tier: int = 0,
    count_delta: int = 0,
    duration_score: float = 0.5,
    fingerprint_hit: bool = False,
    source_weight: float = 0.9,
    flags: list[str] | None = None,
) -> AlbumScore:
    return AlbumScore(
        album=album,
        text_tier=text_tier,
        count_delta=count_delta,
        duration_score=duration_score,
        fingerprint_hit=fingerprint_hit,
        source_weight=source_weight,
        total_score=total_score,
        flags=flags or [],
    )


class TestShouldPrompt:
    def test_empty_list_returns_false(self):
        assert should_prompt([]) is False

    def test_high_score_no_flags_returns_false(self):
        album = _album("Artist", "Album", "musicbrainz", "1", [200.0, 200.0])
        scored = [_score(album, total_score=0.80)]
        assert should_prompt(scored) is False

    def test_low_score_returns_true(self):
        album = _album("Artist", "Album", "musicbrainz", "1", [200.0, 200.0])
        scored = [_score(album, total_score=0.40)]
        assert should_prompt(scored) is True

    def test_small_gap_between_top_two_returns_true(self):
        a = _album("Artist", "Album A", "musicbrainz", "1", [200.0, 200.0])
        b = _album("Artist", "Album B", "netease", "2", [200.0, 200.0])
        scored = [
            _score(a, total_score=0.70),
            _score(b, total_score=0.65),
        ]
        assert should_prompt(scored) is True

    def test_large_gap_returns_false(self):
        a = _album("Artist", "Album A", "musicbrainz", "1", [200.0, 200.0])
        b = _album("Artist", "Album B", "netease", "2", [200.0, 200.0])
        scored = [
            _score(a, total_score=0.80),
            _score(b, total_score=0.50),
        ]
        assert should_prompt(scored) is False

    def test_flags_on_top_candidate_returns_true(self):
        album = _album("Artist", "Album", "musicbrainz", "1", [200.0, 200.0])
        scored = [_score(album, total_score=0.80, flags=["track_count_mismatch"])]
        assert should_prompt(scored) is True

    def test_score_exactly_at_threshold_returns_false(self):
        album = _album("Artist", "Album", "musicbrainz", "1", [200.0, 200.0])
        scored = [_score(album, total_score=0.50)]
        assert should_prompt(scored) is False

    def test_gap_exactly_at_threshold_returns_false(self):
        a = _album("Artist", "Album A", "musicbrainz", "1", [200.0, 200.0])
        b = _album("Artist", "Album B", "netease", "2", [200.0, 200.0])
        scored = [
            _score(a, total_score=0.72),
            _score(b, total_score=0.60),
        ]
        assert should_prompt(scored) is False


class TestSelectAlbumAutoMode:
    def test_interactive_false_returns_top_scored(self):
        a = _album("Artist", "Album A", "musicbrainz", "1", [200.0])
        b = _album("Artist", "Album B", "netease", "2", [200.0])
        scored = [
            _score(a, total_score=0.80),
            _score(b, total_score=0.50),
        ]
        from cue_finder.core.interactive import select_album

        result = select_album(scored, interactive=False, query="test", boundaries=[], total_duration=200.0)
        assert result is a

    def test_interactive_none_high_score_returns_top(self):
        a = _album("Artist", "Album A", "musicbrainz", "1", [200.0])
        scored = [_score(a, total_score=0.80)]
        from cue_finder.core.interactive import select_album

        result = select_album(scored, interactive=None, query="test", boundaries=[], total_duration=200.0)
        assert result is a

    def test_empty_scored_raises_value_error(self):
        from cue_finder.core.interactive import select_album

        try:
            select_album([], interactive=False, query="test", boundaries=[], total_duration=200.0)
            assert False, "Should have raised ValueError"
        except ValueError:
            pass


class TestFormatFlags:
    def test_empty_flags_returns_dash(self):
        assert _format_flags([], 0) == "—"

    def test_track_count_mismatch(self):
        result = _format_flags(["track_count_mismatch"], 2)
        assert "count!Δ2" in result

    def test_duration_mismatch(self):
        result = _format_flags(["duration_mismatch"], 0)
        assert "dur!" in result

    def test_both_flags(self):
        result = _format_flags(["track_count_mismatch", "duration_mismatch"], 1)
        assert "count!Δ1" in result
        assert "dur!" in result


class TestScoreStyle:
    def test_high_score_green(self):
        assert _score_style(0.80) == "green"

    def test_medium_score_yellow(self):
        assert _score_style(0.50) == "yellow"

    def test_low_score_red(self):
        assert _score_style(0.30) == "red"

    def test_boundary_06_green(self):
        assert _score_style(0.60) == "green"

    def test_boundary_04_yellow(self):
        assert _score_style(0.40) == "yellow"


class TestFormatDuration:
    def test_zero_returns_dash(self):
        assert _format_duration(0.0) == "—"

    def test_negative_returns_dash(self):
        assert _format_duration(-1.0) == "—"

    def test_seconds_only(self):
        assert _format_duration(45.0) == "0:45"

    def test_minutes_and_seconds(self):
        assert _format_duration(125.0) == "2:05"

    def test_exact_minute(self):
        assert _format_duration(60.0) == "1:00"

    def test_long_duration(self):
        assert _format_duration(3661.0) == "61:01"


class TestSelectionAborted:
    def test_is_exception(self):
        assert issubclass(SelectionAborted, Exception)

    def test_can_raise_and_catch(self):
        try:
            raise SelectionAborted("test")
        except SelectionAborted as e:
            assert "test" in str(e)


class TestShouldSplitDisc:
    def test_multi_disc_triggers(self):
        album = _album("S.H.E", "Forever", "itunes", "1", [200.0] * 17)
        assert should_split_disc(album, 10) is True

    def test_single_disc_no_trigger(self):
        album = _album("S.H.E", "Play", "itunes", "1", [200.0] * 11)
        assert should_split_disc(album, 10) is False

    def test_small_difference_no_trigger(self):
        album = _album("S.H.E", "Album", "itunes", "1", [200.0] * 13)
        assert should_split_disc(album, 10) is False

    def test_zero_detected_no_trigger(self):
        album = _album("S.H.E", "Album", "itunes", "1", [200.0] * 17)
        assert should_split_disc(album, 0) is False

    def test_exact_double_triggers(self):
        album = _album("S.H.E", "Album", "itunes", "1", [200.0] * 20)
        assert should_split_disc(album, 10) is True

    def test_below_ratio_no_trigger(self):
        album = _album("S.H.E", "Album", "itunes", "1", [200.0] * 14)
        assert should_split_disc(album, 10) is False


class TestParseRange:
    def test_dash_format(self):
        assert parse_range("1-10") == (1, 10)

    def test_colon_format(self):
        assert parse_range("11:17") == (11, 17)

    def test_single_number(self):
        assert parse_range("5") == (5, 5)

    def test_with_spaces(self):
        assert parse_range("  3 - 12  ") == (3, 12)

    def test_invalid_returns_none(self):
        assert parse_range("abc") is None

    def test_partial_invalid_returns_none(self):
        assert parse_range("1-abc") is None

    def test_empty_returns_none(self):
        assert parse_range("") is None


class TestCreateDiscSubset:
    def test_subset_first_half(self):
        album = _album("S.H.E", "Forever", "itunes", "1", [200.0] * 17)
        subset = create_disc_subset(album, 1, 10)
        assert len(subset.tracks) == 10
        assert subset.tracks[0].title == "Track 1"
        assert subset.tracks[9].title == "Track 10"
        assert subset.artist == album.artist
        assert subset.source == album.source

    def test_subset_second_half(self):
        album = _album("S.H.E", "Forever", "itunes", "1", [200.0] * 17)
        subset = create_disc_subset(album, 11, 17)
        assert len(subset.tracks) == 7
        assert subset.tracks[0].title == "Track 11"
        assert subset.tracks[6].title == "Track 17"

    def test_subset_title_includes_range(self):
        album = _album("S.H.E", "Forever", "itunes", "1", [200.0] * 17)
        subset = create_disc_subset(album, 1, 10)
        assert "1-10" in subset.title

    def test_subset_single_track(self):
        album = _album("S.H.E", "Forever", "itunes", "1", [200.0] * 17)
        subset = create_disc_subset(album, 5, 5)
        assert len(subset.tracks) == 1
        assert subset.tracks[0].title == "Track 5"


class TestSuggestDiscRanges:
    def test_17_vs_10_suggests_two_discs(self):
        suggestions = _suggest_disc_ranges(17, 10)
        labels = [s[0] for s in suggestions]
        assert "Disc 1" in labels
        assert "Disc 2" in labels
        disc1 = [s for s in suggestions if s[0] == "Disc 1"][0]
        assert disc1[1] == 1 and disc1[2] == 10
        disc2 = [s for s in suggestions if s[0] == "Disc 2"][0]
        assert disc2[1] == 11 and disc2[2] == 17

    def test_20_vs_10_suggests_half_split(self):
        suggestions = _suggest_disc_ranges(20, 10)
        labels = [s[0] for s in suggestions]
        assert "Disc 1" in labels
        assert "Disc 2" in labels

    def test_no_duplicates(self):
        suggestions = _suggest_disc_ranges(17, 10)
        ranges = [(s[1], s[2]) for s in suggestions]
        assert len(ranges) == len(set(ranges))

    def test_all_ranges_valid(self):
        suggestions = _suggest_disc_ranges(17, 10)
        for _, start, end in suggestions:
            assert 1 <= start <= end <= 17


class TestSearchRefinement:
    def test_dataclass_has_query_field(self):
        from cue_finder.core.interactive import SearchRefinement
        sr = SearchRefinement(query="S.H.E Play 2007")
        assert sr.query == "S.H.E Play 2007"

    def test_dataclass_is_not_album_info(self):
        from cue_finder.core.interactive import SearchRefinement
        sr = SearchRefinement(query="test")
        assert not hasattr(sr, "artist")
        assert not hasattr(sr, "title")


class TestDirectId:
    def test_dataclass_has_source_and_id(self):
        from cue_finder.core.interactive import DirectId
        did = DirectId(source="netease", source_id="12345")
        assert did.source == "netease"
        assert did.source_id == "12345"

    def test_dataclass_is_not_album_info(self):
        from cue_finder.core.interactive import DirectId
        did = DirectId(source="itunes", source_id="456")
        assert not hasattr(did, "artist")
        assert not hasattr(did, "title")
