"""Album candidate scoring: fuse text, duration alignment, track count, source reliability, and AcoustID."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from cue_finder.core.match import TrackMatcher
from cue_finder.core.search import AlbumInfo, _match_tier, _normalize_query_tokens


DEFAULT_SOURCE_WEIGHTS: dict[str, float] = {
    "musicbrainz": 1.0,
    "itunes": 0.9,
    "netease": 0.95,
    "discogs": 0.8,
    "deezer": 0.75,
    "gnudb": 0.6,
    "acoustid": 1.0,
}

_TEXT_WEIGHT = 0.30
_DURATION_WEIGHT = 0.35
_COUNT_WEIGHT = 0.15
_SOURCE_WEIGHT = 0.10
_FINGERPRINT_WEIGHT = 0.10


@dataclass
class AlbumScore:
    """Scoring result for a single album candidate."""

    album: AlbumInfo
    text_tier: int
    count_delta: int
    duration_score: float
    fingerprint_hit: bool
    source_weight: float
    total_score: float
    flags: list[str] = field(default_factory=list)
    year_match: bool = False
    barcode_match: bool = False
    catalog_match: bool = False
    track_name_similarity: float = 0.0
    country_hint: str | None = None
    disambiguation: str | None = None


def score_candidates(
    albums: list[AlbumInfo],
    boundaries: list[float],
    total_duration: float,
    query: str,
    fingerprint_release_ids: set[str] | None = None,
    source_weights: dict[str, float] | None = None,
) -> list[AlbumScore]:
    """Rank album candidates by fusing text and structural signals.

    The returned list is sorted by descending ``total_score``.

    Args:
        albums: Candidate albums from one or more metadata sources.
        boundaries: Detected silence boundaries in seconds.
        total_duration: Total audio length in seconds.
        query: Original user query, used for text-similarity scoring.
        fingerprint_release_ids: Optional set of source IDs that AcoustID
            identified as likely matches.
        source_weights: Optional per-source prior weights. Defaults favor
            MusicBrainz/NetEase over GNDB/Deezer.
    """
    weights = source_weights or DEFAULT_SOURCE_WEIGHTS
    fp_ids = fingerprint_release_ids or set()
    query_tokens = _normalize_query_tokens(query)

    matcher = TrackMatcher()
    scored: list[AlbumScore] = []
    n_segments = len(boundaries) + 1

    for album in albums:
        text_tier = _match_tier(query_tokens, album)
        n_tracks = len(album.tracks)
        count_delta = abs(n_tracks - n_segments)

        track_durations = [t.duration_sec or 0.0 for t in album.tracks]
        try:
            matches = matcher.match(
                boundaries,
                track_durations,
                [t.title for t in album.tracks],
                [t.artist or album.artist for t in album.tracks],
                total_duration,
            )
            duration_score = (
                float(np.mean([m.confidence for m in matches])) if matches else 0.0
            )
        except Exception:
            duration_score = 0.0

        if count_delta == 0:
            count_score = 1.0
        else:
            count_score = max(0.0, 1.0 - count_delta * 0.2)

        source_weight = weights.get(album.source, 0.5)
        fingerprint_hit = album.source_id in fp_ids

        text_score = (4 - text_tier) / 4.0
        fingerprint_score = 1.0 if fingerprint_hit else 0.0

        total = (
            _TEXT_WEIGHT * text_score
            + _DURATION_WEIGHT * duration_score
            + _COUNT_WEIGHT * count_score
            + _SOURCE_WEIGHT * source_weight
            + _FINGERPRINT_WEIGHT * fingerprint_score
        )

        flags: list[str] = []
        if count_delta > 0:
            flags.append("track_count_mismatch")
        if duration_score < 0.5:
            flags.append("duration_mismatch")

        scored.append(
            AlbumScore(
                album=album,
                text_tier=text_tier,
                count_delta=count_delta,
                duration_score=duration_score,
                fingerprint_hit=fingerprint_hit,
                source_weight=source_weight,
                total_score=total,
                flags=flags,
            )
        )

    scored.sort(key=lambda item: item.total_score, reverse=True)
    return scored
