"""Tests for AcoustID fingerprint integration."""

from unittest.mock import MagicMock, patch

import pytest

from cue_finder.core.search import (
    AlbumInfo,
    TrackInfo,
    _acoustid_fingerprint_releases,
    fingerprint_file_with_ids,
)


def _make_album(source_id: str, durations: list[float]) -> AlbumInfo:
    return AlbumInfo(
        artist="S.H.E",
        title="Encore",
        date=None,
        source="musicbrainz",
        source_id=source_id,
        tracks=[
            TrackInfo(title=f"Track {i + 1}", duration_sec=d, artist="S.H.E")
            for i, d in enumerate(durations)
        ],
    )


class TestAcoustidFingerprintReleases:
    def test_returns_release_mbids_sorted_by_score(self):
        mock_mod = MagicMock()
        mock_mod.fingerprint_file.return_value = (123.0, "fp")
        mock_mod.lookup.return_value = {
            "status": "ok",
            "results": [
                {
                    "score": 0.9,
                    "recordings": [
                        {
                            "releases": [
                                {"id": "mbid-a"},
                                {"id": "mbid-b"},
                            ]
                        }
                    ],
                },
                {
                    "score": 0.5,
                    "recordings": [
                        {
                            "releases": [
                                {"id": "mbid-c"},
                            ]
                        }
                    ],
                },
            ],
        }

        with patch.dict("os.environ", {"ACOUSTID_API_KEY": "test-key"}):
            with patch(
                "cue_finder.core.search.pyacoustid", mock_mod
            ):
                releases = _acoustid_fingerprint_releases("/tmp/fake.flac")

        assert releases == [(0.9, "mbid-a"), (0.9, "mbid-b"), (0.5, "mbid-c")]

    def test_returns_empty_without_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            assert _acoustid_fingerprint_releases("/tmp/fake.flac") == []

    def test_returns_empty_when_backend_unavailable(self):
        with patch.dict("os.environ", {"ACOUSTID_API_KEY": "test-key"}):
            with patch("cue_finder.core.search.pyacoustid", None):
                assert _acoustid_fingerprint_releases("/tmp/fake.flac") == []

    def test_returns_empty_on_fingerprint_failure(self):
        mock_mod = MagicMock()
        mock_mod.fingerprint_file.side_effect = RuntimeError("no backend")

        with patch.dict("os.environ", {"ACOUSTID_API_KEY": "test-key"}):
            with patch("cue_finder.core.search.pyacoustid", mock_mod):
                assert _acoustid_fingerprint_releases("/tmp/fake.flac") == []


class TestFingerprintFileWithIds:
    def test_returns_albums_and_release_ids(self):
        mock_mod = MagicMock()
        mock_mod.fingerprint_file.return_value = (123.0, "fp")
        mock_mod.lookup.return_value = {
            "status": "ok",
            "results": [
                {
                    "score": 0.9,
                    "recordings": [
                        {
                            "releases": [
                                {"id": "mbid-a"},
                            ]
                        }
                    ],
                }
            ],
        }

        expected = _make_album("mbid-a", [200.0, 220.0, 180.0])

        with patch.dict("os.environ", {"ACOUSTID_API_KEY": "test-key"}):
            with patch("cue_finder.core.search.pyacoustid", mock_mod):
                with patch(
                    "cue_finder.core.search._musicbrainz_fetch",
                    return_value=expected,
                ):
                    albums, release_ids = fingerprint_file_with_ids(
                        "/tmp/fake.flac"
                    )

        assert release_ids == {"mbid-a"}
        assert len(albums) == 1
        assert albums[0].source_id == "mbid-a"

    def test_returns_empty_when_no_matches(self):
        with patch.dict("os.environ", {"ACOUSTID_API_KEY": "test-key"}):
            with patch(
                "cue_finder.core.search._acoustid_fingerprint_releases",
                return_value=[],
            ):
                albums, release_ids = fingerprint_file_with_ids("/tmp/fake.flac")

        assert albums == []
        assert release_ids == set()
