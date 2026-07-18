"""Multi-source metadata search module with cascading fallback."""

from __future__ import annotations

import importlib
import os
import re
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Callable, NamedTuple

import requests


class SearchTierResult(NamedTuple):
    tier: int
    albums: list[AlbumInfo]
    suggestions: list[str]

musicbrainzngs: Any = None
try:
    musicbrainzngs = importlib.import_module("musicbrainzngs")
except Exception:
    pass

discogs_client: Any = None
try:
    discogs_client = importlib.import_module("discogs_client")
except Exception:
    pass

deezer: Any = None
try:
    deezer = importlib.import_module("deezer")
except Exception:
    pass

pyncm: Any = True  # NetEase uses raw requests, always available

pyacoustid: Any = None
try:
    pyacoustid = importlib.import_module("acoustid")
except Exception:
    pass


@dataclass
class TrackInfo:
    """Normalized track representation."""

    title: str
    duration_sec: float | None
    artist: str | None = None


@dataclass
class AlbumInfo:
    """Normalized album representation."""

    artist: str
    title: str
    date: str | None
    source: str
    source_id: str
    tracks: list[TrackInfo] = field(default_factory=list)


DEFAULT_SOURCES = (
    "musicbrainz",
    "itunes",
    "netease",
    "discogs",
    "deezer",
    "gnudb",
)

_SOURCE_DELAYS = {
    "musicbrainz": 1.0,
    "itunes": 0.2,
    "netease": 0.2,
    "discogs": 1.0,
    "deezer": 0.2,
    "gnudb": 1.0,
    "acoustid": 0.5,
}

_last_request_time: dict[str, float] = {}


def _rate_limit(source: str) -> None:
    delay = _SOURCE_DELAYS.get(source, 0.0)
    if delay <= 0:
        return
    last = _last_request_time.get(source, 0.0)
    elapsed = time.monotonic() - last
    if elapsed < delay:
        time.sleep(delay - elapsed)
    _last_request_time[source] = time.monotonic()


def _retry_with_backoff(
    source: str, max_retries: int = 3
) -> Callable[[Callable[[], Any]], Any]:
    def _retry(func: Callable[[], Any]) -> Any:
        for attempt in range(max_retries + 1):
            try:
                _rate_limit(source)
                return func()
            except Exception as exc:
                if attempt >= max_retries:
                    raise
                message = str(exc).lower()
                status_code = getattr(exc, "status_code", None) or getattr(
                    exc, "code", None
                )
                if status_code in (429, 503) or "rate" in message or "503" in message:
                    time.sleep(2**attempt)
                    continue
                raise
        return None

    return _retry


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_duration_string(value: str | None) -> float | None:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    parts = value.split(":")
    try:
        numeric_parts = [float(part) for part in parts]
    except ValueError:
        return None
    if not numeric_parts:
        return None
    total = 0.0
    for part in numeric_parts:
        total = total * 60 + part
    return total


def _check_source_available(name: str) -> bool:
    if name == "musicbrainz":
        return musicbrainzngs is not None
    if name == "itunes":
        return True
    if name == "netease":
        return pyncm is not None
    if name == "discogs":
        return discogs_client is not None and bool(os.environ.get("DISCOGS_TOKEN"))
    if name == "deezer":
        return deezer is not None
    if name == "gnudb":
        return True
    if name == "acoustid":
        return pyacoustid is not None and bool(os.environ.get("ACOUSTID_API_KEY"))
    return False


def _musicbrainz_search(query: str) -> list[AlbumInfo]:
    if musicbrainzngs is None:
        return []
    musicbrainzngs.set_useragent("cue-finder", "0.1")

    def _do_search() -> dict[str, Any]:
        return musicbrainzngs.search_releases(query=query, limit=10)

    try:
        result = _retry_with_backoff("musicbrainz")(_do_search)
    except Exception:
        return []

    releases = result.get("release-list", []) if result else []
    albums: list[AlbumInfo] = []
    # Only fetch the top few releases; downstream cross-source ranking will
    # demote MusicBrainz results when another source has a stronger match,
    # so fetching all 10 is usually wasted time and API calls.
    for release in releases[:3]:
        release_id = release.get("id")
        if not release_id:
            continue
        album = _musicbrainz_fetch(release_id)
        if album and album.tracks and all(t.duration_sec is not None for t in album.tracks):
            albums.append(album)
    return albums


def _musicbrainz_fetch(release_id: str) -> AlbumInfo | None:
    if musicbrainzngs is None:
        return None
    musicbrainzngs.set_useragent("cue-finder", "0.1")

    def _do_fetch() -> dict[str, Any]:
        return musicbrainzngs.get_release_by_id(
            release_id, includes=["recordings", "media"]
        )

    try:
        result = _retry_with_backoff("musicbrainz")(_do_fetch)
    except Exception:
        return None

    release = result.get("release", {}) if result else {}
    artist = _musicbrainz_artist_name(release.get("artist-credit", []))
    title = release.get("title", "")
    date = release.get("date") or None
    tracks: list[TrackInfo] = []
    for medium in release.get("medium-list", []):
        for track in medium.get("track-list", []):
            recording = track.get("recording", {})
            track_title = recording.get("title") or track.get("title", "")
            length_ms = recording.get("length")
            duration = None
            if length_ms is not None:
                duration = _safe_float(length_ms)
                if duration is not None:
                    duration = duration / 1000.0
            track_artist = _musicbrainz_artist_name(track.get("artist-credit", [])) or artist
            tracks.append(TrackInfo(title=track_title, duration_sec=duration, artist=track_artist))
    return AlbumInfo(
        artist=artist,
        title=title,
        date=date,
        source="musicbrainz",
        source_id=release_id,
        tracks=tracks,
    )


def _musicbrainz_artist_name(artist_credit: list[dict[str, Any]]) -> str:
    if not artist_credit:
        return ""
    parts: list[str] = []
    for item in artist_credit:
        artist = item.get("artist", {})
        name = artist.get("name", "")
        if name:
            parts.append(name)
        join_phrase = item.get("joinphrase", "")
        if join_phrase:
            parts.append(join_phrase.strip())
    return " ".join(parts).strip()


def _itunes_search(query: str) -> list[AlbumInfo]:
    url = "https://itunes.apple.com/search"
    params = {
        "term": query,
        "entity": "album",
        "limit": "10",
    }

    def _do_search() -> dict[str, Any]:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    try:
        result = _retry_with_backoff("itunes")(_do_search)
    except Exception:
        return []

    albums: list[AlbumInfo] = []
    for album in result.get("results", []):
        collection_id = album.get("collectionId")
        if not collection_id:
            continue
        fetched = _itunes_fetch(collection_id)
        if fetched and fetched.tracks and all(t.duration_sec is not None for t in fetched.tracks):
            albums.append(fetched)
    return albums


def _itunes_fetch(album_id: int | str) -> AlbumInfo | None:
    url = "https://itunes.apple.com/lookup"
    params = {"id": str(album_id), "entity": "song"}

    def _do_fetch() -> dict[str, Any]:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    try:
        result = _retry_with_backoff("itunes")(_do_fetch)
    except Exception:
        return None

    album_data: dict[str, Any] | None = None
    tracks: list[TrackInfo] = []
    for item in result.get("results", []):
        if item.get("wrapperType") == "collection" and item.get("collectionType") == "Album":
            album_data = item
        elif item.get("wrapperType") == "track" and item.get("kind") == "song":
            duration_ms = item.get("trackTimeMillis")
            duration = None
            if duration_ms is not None:
                duration = _safe_float(duration_ms)
                if duration is not None:
                    duration = duration / 1000.0
            tracks.append(
                TrackInfo(
                    title=item.get("trackName", ""),
                    duration_sec=duration,
                    artist=item.get("artistName"),
                )
            )

    if album_data is None:
        return None

    tracks = sorted(tracks, key=lambda t: t.duration_sec or 0.0)
    artist = album_data.get("artistName", "")
    title = album_data.get("collectionName", "")
    release_date = album_data.get("releaseDate", "")[:10] or None
    return AlbumInfo(
        artist=artist,
        title=title,
        date=release_date,
        source="itunes",
        source_id=str(album_id),
        tracks=tracks,
    )


def _netease_search(query: str) -> list[AlbumInfo]:
    """Search NetEase Cloud Music using public search API."""
    try:
        response = requests.get(
            "https://music.163.com/api/search/get",
            params={"s": query, "type": 10, "limit": 10, "offset": 0},
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://music.163.com/"},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
    except Exception:
        return []

    if data.get("code") != 200:
        return []

    albums: list[AlbumInfo] = []
    for album in (data.get("result", {}) or {}).get("albums", []):
        album_id = album.get("id")
        if not album_id:
            continue
        fetched = _netease_fetch(album_id)
        if fetched and fetched.tracks and all(
            t.duration_sec is not None for t in fetched.tracks
        ):
            albums.append(fetched)
    return albums


def _netease_fetch(album_id: int | str) -> AlbumInfo | None:
    """Fetch full album info from NetEase Cloud Music.

    Uses the ``/api/v1/album`` endpoint, which still returns track lists for
    many region-restricted albums that the older ``/api/album`` endpoint
    rejects with ``code=-462`` (phone-verification gate).
    """
    try:
        response = requests.get(
            f"https://music.163.com/api/v1/album/{album_id}",
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://music.163.com/"},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
    except Exception:
        return None

    if data.get("code") != 200:
        return None

    album = data.get("album", {}) if data else {}
    songs = data.get("songs", []) if data else []

    artist = _netease_artist_name(album.get("artist", {}))
    title = album.get("name", "")
    publish_time = album.get("publishTime")
    date = None
    if publish_time:
        try:
            date = time.strftime("%Y-%m-%d", time.localtime(publish_time / 1000))
        except Exception:
            date = str(publish_time)

    tracks: list[TrackInfo] = []
    for song in songs:
        duration_ms = song.get("dt")
        duration = None
        if duration_ms is not None:
            duration = _safe_float(duration_ms)
            if duration is not None:
                duration = duration / 1000.0
        track_artist = _netease_artist_name(song.get("ar", []))
        tracks.append(
            TrackInfo(
                title=song.get("name", ""),
                duration_sec=duration,
                artist=track_artist,
            )
        )
    return AlbumInfo(
        artist=artist,
        title=title,
        date=date,
        source="netease",
        source_id=str(album_id),
        tracks=tracks,
    )


def _netease_artist_name(artist_data: Any) -> str:
    if isinstance(artist_data, dict):
        return artist_data.get("name", "")
    if isinstance(artist_data, list) and artist_data:
        names = [a.get("name", "") for a in artist_data if isinstance(a, dict)]
        return ", ".join(name for name in names if name)
    return ""


def _discogs_search(query: str) -> list[AlbumInfo]:
    token = os.environ.get("DISCOGS_TOKEN")
    if discogs_client is None or not token:
        return []
    client = discogs_client.Client("cue-finder/0.1", user_token=token)

    def _do_search() -> list[Any]:
        return list(client.search(query, type="release"))

    try:
        results = _retry_with_backoff("discogs")(_do_search)
    except Exception:
        return []

    albums: list[AlbumInfo] = []
    for release in results[:10]:
        try:
            release_id = release.id
        except Exception:
            continue
        album = _discogs_fetch(str(release_id))
        if album and album.tracks and all(t.duration_sec is not None for t in album.tracks):
            albums.append(album)
    return albums


def _discogs_fetch(release_id: str) -> AlbumInfo | None:
    token = os.environ.get("DISCOGS_TOKEN")
    if not token or discogs_client is None:
        return None
    client = discogs_client.Client("cue-finder/0.1", user_token=token)

    def _do_fetch() -> Any:
        return client.release(int(release_id))

    try:
        release = _retry_with_backoff("discogs")(_do_fetch)
    except Exception:
        return None

    try:
        release.refresh()
    except Exception:
        pass

    artist_parts = []
    try:
        artists = release.artists
    except Exception:
        artists = []
    for artist in artists:
        try:
            artist_parts.append(artist.name)
        except Exception:
            continue
    artist = ", ".join(artist_parts)

    title = ""
    try:
        title = release.title
    except Exception:
        pass

    year = None
    try:
        year = str(release.year) if release.year else None
    except Exception:
        pass

    tracks: list[TrackInfo] = []
    try:
        tracklist = release.tracklist
    except Exception:
        tracklist = []
    for track in tracklist:
        try:
            track_title = track.title
        except Exception:
            track_title = ""
        duration = _parse_duration_string(getattr(track, "duration", None))
        track_artist = artist
        try:
            track_artists = track.artists
            if track_artists:
                track_artist = ", ".join(a.name for a in track_artists)
        except Exception:
            pass
        tracks.append(TrackInfo(title=track_title, duration_sec=duration, artist=track_artist))

    if not tracks or any(t.duration_sec is None for t in tracks):
        return None

    return AlbumInfo(
        artist=artist,
        title=title,
        date=year,
        source="discogs",
        source_id=release_id,
        tracks=tracks,
    )


def _deezer_search(query: str) -> list[AlbumInfo]:
    if deezer is None:
        return []
    client = deezer.Client()

    def _do_search() -> list[Any]:
        return client.search_albums(query)

    try:
        results = _retry_with_backoff("deezer")(_do_search)
    except Exception:
        return []

    albums: list[AlbumInfo] = []
    for album in results[:10]:
        try:
            album_id = album.id
        except Exception:
            continue
        fetched = _deezer_fetch(str(album_id))
        if fetched and fetched.tracks and all(t.duration_sec is not None for t in fetched.tracks):
            albums.append(fetched)
    return albums


def _deezer_fetch(album_id: str) -> AlbumInfo | None:
    if deezer is None:
        return None
    client = deezer.Client()

    def _do_get_album() -> Any:
        return client.get_album(int(album_id))

    try:
        album = _retry_with_backoff("deezer")(_do_get_album)
    except Exception:
        return None

    try:
        artist = album.artist.name if album.artist else ""
    except Exception:
        artist = ""
    try:
        title = album.title or ""
    except Exception:
        title = ""
    try:
        release_date = album.release_date or None
    except Exception:
        release_date = None

    tracks: list[TrackInfo] = []
    try:
        album_tracks = album.get_tracks()
    except Exception:
        album_tracks = []
    for track in album_tracks:
        try:
            track_title = track.title or ""
        except Exception:
            track_title = ""
        try:
            track_artist = track.artist.name if track.artist else artist
        except Exception:
            track_artist = artist
        try:
            duration = float(track.duration) if track.duration is not None else None
        except Exception:
            duration = None
        tracks.append(TrackInfo(title=track_title, duration_sec=duration, artist=track_artist))

    return AlbumInfo(
        artist=artist,
        title=title,
        date=release_date,
        source="deezer",
        source_id=album_id,
        tracks=tracks,
    )


def _gnudb_search(query: str) -> list[AlbumInfo]:
    encoded_query = urllib.parse.quote_plus(query)
    url = (
        f"http://gnudb.gnudb.org/~cddb/cddb.cgi?cmd=cddb+query+{encoded_query}"
        f"&hello=cuefinder@localhost+cue-finder+0.1&proto=6"
    )

    def _do_search() -> str:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.text

    try:
        text = _retry_with_backoff("gnudb")(_do_search)
    except Exception:
        return []

    albums: list[AlbumInfo] = []
    for line in text.splitlines():
        if line.startswith("200"):
            parts = line.split(" ", 3)
            if len(parts) >= 4:
                discid = parts[1]
                album = _gnudb_fetch(discid)
                if album and album.tracks and all(t.duration_sec is not None for t in album.tracks):
                    albums.append(album)
                    break
        elif line.startswith("211") or line.startswith("210"):
            continue
        elif re.match(r"^[0-9a-zA-Z]+\s+", line):
            parts = line.split(" ", 2)
            if len(parts) >= 3:
                discid = parts[1]
                album = _gnudb_fetch(discid)
                if album and album.tracks and all(t.duration_sec is not None for t in album.tracks):
                    albums.append(album)
    return albums[:10]


def _gnudb_fetch(discid: str) -> AlbumInfo | None:
    url = (
        f"http://gnudb.gnudb.org/~cddb/cddb.cgi?cmd=cddb+read+misc+{discid}"
        f"&hello=cuefinder@localhost+cue-finder+0.1&proto=6"
    )

    def _do_fetch() -> str:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.text

    try:
        text = _retry_with_backoff("gnudb")(_do_fetch)
    except Exception:
        return None

    if not text.startswith("210") and not text.startswith("200"):
        return None

    dtitle = ""
    dyear: str | None = None
    offsets: list[int] = []
    tracks: list[TrackInfo] = []
    for line in text.splitlines()[1:]:
        if line.startswith("DTITLE="):
            dtitle = line.split("=", 1)[1].strip()
        elif line.startswith("DYEAR="):
            dyear = line.split("=", 1)[1].strip() or None
        elif line.startswith("TTITLE"):
            idx_title = line.split("=", 1)
            if len(idx_title) == 2:
                tracks.append(TrackInfo(title=idx_title[1].strip(), duration_sec=None, artist=None))
        elif re.match(r"^\d+\s", line):
            try:
                offsets.append(int(line.split()[0]))
            except ValueError:
                pass

    if len(tracks) > 1 and len(offsets) == len(tracks):
        for i in range(len(tracks) - 1):
            duration_frames = offsets[i + 1] - offsets[i]
            tracks[i].duration_sec = duration_frames / 75.0

    if not tracks or all(t.duration_sec is None for t in tracks):
        return None

    artist = ""
    title = dtitle
    if " / " in dtitle:
        artist, title = dtitle.split(" / ", 1)
    return AlbumInfo(
        artist=artist,
        title=title,
        date=dyear,
        source="gnudb",
        source_id=discid,
        tracks=tracks,
    )


def _acoustid_fingerprint_releases(file_path: str) -> list[tuple[float, str]]:
    """Fingerprint ``file_path`` and return AcoustID-matched release MBIDs.

    Each returned tuple is ``(score, release_mbid)`` sorted by descending
    score. An empty list means fingerprinting failed, no API key is
    configured, or the backend is unavailable.
    """
    api_key = os.environ.get("ACOUSTID_API_KEY")
    if pyacoustid is None or not api_key:
        return []

    try:
        duration, fingerprint = _retry_with_backoff("acoustid")(
            lambda: pyacoustid.fingerprint_file(file_path)
        )
    except Exception:
        return []

    try:
        response = _retry_with_backoff("acoustid")(
            lambda: pyacoustid.lookup(
                api_key, fingerprint, duration, meta=["recordings", "releaseids"]
            )
        )
    except Exception:
        return []

    if not isinstance(response, dict) or response.get("status") != "ok":
        return []

    releases: list[tuple[float, str]] = []
    for result in response.get("results", []):
        score = result.get("score") or 0.0
        for recording in result.get("recordings", []):
            for release in recording.get("releases", []):
                mbid = release.get("id")
                if mbid:
                    releases.append((float(score), str(mbid)))

    releases.sort(key=lambda pair: pair[0], reverse=True)
    return releases


def _search_albums_by_recording_mbid(mbid: str) -> list[AlbumInfo]:
    if musicbrainzngs is None:
        return []
    musicbrainzngs.set_useragent("cue-finder", "0.1")

    def _do_lookup() -> dict[str, Any]:
        return musicbrainzngs.get_recording_by_id(
            mbid, includes=["releases"]
        )

    try:
        result = _retry_with_backoff("musicbrainz")(_do_lookup)
    except Exception:
        return []

    recording = result.get("recording", {}) if result else {}
    albums: list[AlbumInfo] = []
    for release in recording.get("release-list", [])[:5]:
        release_id = release.get("id")
        if not release_id:
            continue
        album = _musicbrainz_fetch(release_id)
        if album and album.tracks and all(t.duration_sec is not None for t in album.tracks):
            albums.append(album)
    return albums


_SOURCE_SEARCHERS = {
    "musicbrainz": _musicbrainz_search,
    "itunes": _itunes_search,
    "netease": _netease_search,
    "discogs": _discogs_search,
    "deezer": _deezer_search,
    "gnudb": _gnudb_search,
}

_SOURCE_FETCHERS = {
    "musicbrainz": _musicbrainz_fetch,
    "itunes": _itunes_fetch,
    "netease": _netease_fetch,
    "discogs": _discogs_fetch,
    "deezer": _deezer_fetch,
}


_CJK_RANGE = r"\u4e00-\u9fff\u3400-\u4dbf\uff00-\uffef"
_KEEP_CHARS = rf"a-zA-Z0-9{_CJK_RANGE}"


def _normalize_query_tokens(text: str | None) -> list[str]:
    """Tokenize a query for similarity matching.

    Collapse ``S.H.E``-style dotted abbreviations into ``she`` (single token)
    so that explicit artist names survive source-side token boundary quirks,
    and strip standalone punctuation noise.
    """
    if not text:
        return []
    lowered = text.lower()
    # "S.H.E" → "she"; "U.S.A" → "usa"; "L.L." → "ll"
    collapsed = re.sub(r"(?<=[a-z])\.(?=[a-z])", "", lowered)
    # Anything not letter/digit/CJK becomes a separator
    tokens = re.findall(rf"[{_CJK_RANGE}a-z0-9]+", collapsed, flags=re.UNICODE)
    return tokens


def _match_tier(query_tokens: list[str], album: AlbumInfo) -> int:
    """Categorize how well ``album`` matches into one of five tiers.

    Lower is better. Tiers preserve source order on ties, so when several
    albums from the same source fall into the same tier, the source's own
    relevance ranking wins (e.g. iTunes puts S.H.E's "安可" above the live
    "2gether 4ever Encore 演唱會" for "S.H.E ENCORE").

    Tier 0: artist tokens ⊆ query AND title tokens ⊆ query.
            The strongest signal; covers "Pink Floyd Dark Side of the Moon"
            where the target album's full title is in the query, while
            "The Wall" only matches the artist.
    Tier 1: artist tokens ⊆ query but title is NOT a full subset.
            Covers CJK albums whose Chinese title has no Latin overlap with
            the English query (e.g. S.H.E "安可" for the query "S.H.E ENCORE").
    Tier 2: partial artist overlap only.
    Tier 3: no artist overlap, but title overlaps with the query.
    Tier 4: nothing matches.
    """
    if not query_tokens:
        return 4
    query_set = set(query_tokens)
    artist_tokens = set(_normalize_query_tokens(album.artist))
    title_tokens = set(_normalize_query_tokens(album.title))

    artist_full_match = bool(artist_tokens and artist_tokens.issubset(query_set))
    title_full_match = bool(title_tokens and title_tokens.issubset(query_set))

    if artist_full_match and title_full_match:
        return 0
    if artist_full_match:
        return 1
    if artist_tokens and (artist_tokens & query_set):
        return 2
    if title_tokens and (title_tokens & query_set):
        return 3
    return 4


def _rank_albums_by_similarity(
    query: str, albums: list[AlbumInfo]
) -> list[AlbumInfo]:
    """Stable-sort ``albums`` by match tier (best first), source order within tier.

    The original index encodes ``DEFAULT_SOURCES`` priority plus each
    source's own relevance ranking, so a tier tie still prefers the source
    the user configured first and the result that source returned first.
    """
    query_tokens = _normalize_query_tokens(query)
    if not query_tokens:
        return albums
    ranked = sorted(
        enumerate(albums),
        key=lambda pair: (_match_tier(query_tokens, pair[1]), pair[0]),
    )
    return [album for _, album in ranked]


def search_album(query: str, sources: list[str] | None = None) -> list[AlbumInfo]:
    """Search for album metadata across multiple sources and rank results.

    Args:
        query: Free-text query string (e.g. "Radiohead OK Computer").
        sources: Optional ordered list of source names. When ``None`` the
            default cascade is queried. When a single source is provided
            (e.g. via ``--source itunes``) only that source is queried.

    Returns:
        A list of normalized album results ranked by similarity to the
        query. The best match is ``result[0]`` so the CLI's
        ``search_album(query)[0]`` heuristic picks the right album even when
        the first available source returns irrelevant results (e.g.
        MusicBrainz putting Frank Sinatra first for "S.H.E ENCORE").
    """
    if sources is None:
        sources = list(DEFAULT_SOURCES)

    collected: list[AlbumInfo] = []
    seen: set[tuple[str, str]] = set()
    for source in sources:
        if not _check_source_available(source):
            continue
        searcher = _SOURCE_SEARCHERS.get(source)
        if searcher is None:
            continue
        try:
            results = searcher(query)
        except Exception:
            results = []
        for album in results:
            key = (album.source, album.source_id)
            if key in seen:
                continue
            seen.add(key)
            collected.append(album)

    if not collected:
        return []
    return _rank_albums_by_similarity(query, collected)


def fetch_album(source: str, album_id: str) -> AlbumInfo | None:
    """Fetch a specific album by source name and source album ID.

    Args:
        source: Source name (e.g. "musicbrainz", "netease").
        album_id: Source-specific album identifier.

    Returns:
        Normalized album metadata, or None if the source is unavailable or
        the fetch fails.
    """
    if not _check_source_available(source):
        return None
    fetcher = _SOURCE_FETCHERS.get(source)
    if fetcher is None:
        return None
    try:
        return fetcher(album_id)
    except Exception:
        return None


def identify_file(file_path: str) -> list[AlbumInfo]:
    """Identify a single audio file by AcoustID fingerprint and return albums.

    If fingerprinting yields no matches, falls back to an empty list. This is
    a supplementary identification method intended for ambiguous text queries.

    Args:
        file_path: Path to the audio file to fingerprint.

    Returns:
        A list of normalized album results derived from the fingerprint match.
    """
    albums, _release_ids = fingerprint_file_with_ids(file_path)
    return albums


def fingerprint_file_with_ids(file_path: str) -> tuple[list[AlbumInfo], set[str]]:
    """Fingerprint a file once and return both matched albums and release IDs.

    Returns a tuple of (albums, release_mbid_set). The set can be passed to
    ``score_candidates`` as ``fingerprint_release_ids`` to boost candidates
    that AcoustID identified.
    """
    releases = _acoustid_fingerprint_releases(file_path)
    if not releases:
        return [], set()

    albums: list[AlbumInfo] = []
    release_ids: set[str] = set()
    seen: set[str] = set()
    for _score, mbid in releases:
        if mbid in seen:
            continue
        seen.add(mbid)
        release_ids.add(mbid)
        album = _musicbrainz_fetch(mbid)
        if album and album.tracks and all(t.duration_sec is not None for t in album.tracks):
            albums.append(album)
    return albums, release_ids


def _extract_year_from_query(query: str) -> str | None:
    """Extract a 4-digit year from the query if present."""
    match = re.search(r"\b(19|20)\d{2}\b", query)
    return match.group(0) if match else None


def _extract_barcode_from_query(query: str) -> str | None:
    """Extract a barcode (8-13 digits) from the query if present."""
    match = re.search(r"\b\d{8,13}\b", query)
    return match.group(0) if match else None


def _extract_catalog_from_query(query: str) -> str | None:
    """Extract a catalog number (alphanumeric with hyphens) from the query if present."""
    # Common catalog patterns: ABC-123, ABC123, 123-4567890
    match = re.search(r"\b[A-Z]{2,5}[-]?\d{3,8}\b", query, re.IGNORECASE)
    return match.group(0) if match else None


def _generate_refinement_suggestions(query: str, albums: list[AlbumInfo]) -> list[str]:
    """Generate query refinement suggestions based on signal divergence."""
    suggestions = []
    
    # Suggest adding year if multiple albums have different years
    years = [a.date[:4] for a in albums if a.date and len(a.date) >= 4]
    if len(set(years)) > 1:
        suggestions.append(f"{query} {years[0]}" if years else f"{query} <year>")
    
    # Suggest adding source if multiple sources returned results
    sources = list(set(a.source for a in albums))
    if len(sources) > 1:
        suggestions.append(f"{query} --source {sources[0]}")
    
    # Suggest adding track name if query is very short
    if len(query.split()) <= 2:
        suggestions.append(f"{query} <track-name>")
    
    return suggestions[:3]  # Limit to 3 suggestions


def search_album_progressive(
    query: str,
    sources: list[str] | None = None,
    file_path: str | None = None,
) -> SearchTierResult:
    """Progressive search with three tiers of specificity.
    
    Tier 1: Exact ID Lookup (barcode/ISRC/catalog/source:id in query)
    Tier 2: Text Search with Signal Extraction
    Tier 3: Ambiguous Result with Suggestions
    
    Args:
        query: Free-text query string, may contain identifiers.
        sources: Optional ordered list of source names.
        file_path: Optional audio file path for AcoustID fingerprinting.
    
    Returns:
        SearchTierResult with tier number, albums, and refinement suggestions.
    """
    # Tier 1: Check for exact identifiers in query
    barcode = _extract_barcode_from_query(query)
    catalog = _extract_catalog_from_query(query)
    
    # Check for source:id format
    if ":" in query and not query.startswith("http"):
        parts = query.split(":", 1)
        if len(parts) == 2 and parts[0] in DEFAULT_SOURCES:
            album = fetch_album(parts[0], parts[1])
            if album:
                return SearchTierResult(tier=1, albums=[album], suggestions=[])
    
    # Tier 2: Standard text search with signal extraction
    albums = search_album(query, sources=sources)
    
    if not albums:
        return SearchTierResult(tier=3, albums=[], suggestions=[query])
    
    # If we have a single strong match, return it
    if len(albums) == 1:
        return SearchTierResult(tier=2, albums=albums, suggestions=[])
    
    # Generate refinement suggestions for ambiguous results
    suggestions = _generate_refinement_suggestions(query, albums)
    
    return SearchTierResult(tier=3, albums=albums, suggestions=suggestions)
