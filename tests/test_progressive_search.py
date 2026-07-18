"""Tests for progressive search functionality."""

from cue_finder.core.search import (
    _extract_barcode_from_query,
    _extract_catalog_from_query,
    _extract_year_from_query,
    _generate_refinement_suggestions,
    AlbumInfo,
    TrackInfo,
)


class TestExtractYearFromQuery:
    def test_extracts_4_digit_year(self):
        assert _extract_year_from_query("S.H.E Play 2007") == "2007"

    def test_extracts_year_from_beginning(self):
        assert _extract_year_from_query("2007 S.H.E Play") == "2007"

    def test_no_year_returns_none(self):
        assert _extract_year_from_query("S.H.E Play") is None

    def test_old_year_not_extracted(self):
        assert _extract_year_from_query("S.H.E Play 1800") is None


class TestExtractBarcodeFromQuery:
    def test_extracts_13_digit_barcode(self):
        assert _extract_barcode_from_query("album 1234567890123") == "1234567890123"

    def test_extracts_8_digit_barcode(self):
        assert _extract_barcode_from_query("album 12345678") == "12345678"

    def test_no_barcode_returns_none(self):
        assert _extract_barcode_from_query("S.H.E Play") is None

    def test_short_number_not_barcode(self):
        assert _extract_barcode_from_query("album 123") is None


class TestExtractCatalogFromQuery:
    def test_extracts_catalog_number(self):
        assert _extract_catalog_from_query("album ABC-123") == "ABC-123"

    def test_extracts_alphanumeric_catalog(self):
        assert _extract_catalog_from_query("album EMI4567") == "EMI4567"

    def test_no_catalog_returns_none(self):
        assert _extract_catalog_from_query("S.H.E Play") is None


class TestGenerateRefinementSuggestions:
    def _album(self, artist, title, date, source, source_id):
        return AlbumInfo(
            artist=artist,
            title=title,
            date=date,
            source=source,
            source_id=source_id,
            tracks=[TrackInfo(title="Track 1", duration_sec=200.0, artist=artist)],
        )

    def test_suggests_year_when_multiple_years(self):
        albums = [
            self._album("S.H.E", "Play", "2007-01-01", "itunes", "1"),
            self._album("S.H.E", "Play", "2008-01-01", "netease", "2"),
        ]
        suggestions = _generate_refinement_suggestions("S.H.E Play", albums)
        assert any("2007" in s for s in suggestions)

    def test_suggests_source_when_multiple_sources(self):
        albums = [
            self._album("S.H.E", "Play", "2007-01-01", "itunes", "1"),
            self._album("S.H.E", "Play", "2007-01-01", "netease", "2"),
        ]
        suggestions = _generate_refinement_suggestions("S.H.E Play", albums)
        assert any("--source" in s for s in suggestions)

    def test_suggests_track_name_for_short_query(self):
        albums = [
            self._album("S.H.E", "Play", "2007-01-01", "itunes", "1"),
        ]
        suggestions = _generate_refinement_suggestions("Play", albums)
        assert any("<track-name>" in s for s in suggestions)

    def test_limits_to_3_suggestions(self):
        albums = [
            self._album("S.H.E", "Play", "2007-01-01", "itunes", "1"),
            self._album("S.H.E", "Play", "2008-01-01", "netease", "2"),
        ]
        suggestions = _generate_refinement_suggestions("Play", albums)
        assert len(suggestions) <= 3
