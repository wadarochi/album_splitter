# Metadata Search

## Purpose

Search multiple music metadata sources (MusicBrainz, iTunes, NetEase, Discogs, Deezer, GnuDB) in cascading fallback order and return normalized album and track information.

## Requirements

### Requirement: Multi-source metadata search
The system SHALL search multiple music metadata sources in cascading fallback order: MusicBrainz → iTunes → NetEase Cloud Music → Discogs → Deezer → GnuDB. If a source returns no results or is unavailable, the system SHALL automatically try the next source.

#### Scenario: Album found on first source
- **WHEN** searching for "Radiohead OK Computer"
- **THEN** MusicBrainz SHALL return results first, and the system SHALL NOT query subsequent sources

#### Scenario: Album not on MusicBrainz but on NetEase
- **WHEN** searching for a Chinese indie album not in MusicBrainz
- **THEN** the system SHALL fall through to iTunes, then NetEase, which SHALL return results

#### Scenario: All sources fail
- **WHEN** no source returns results for the query
- **THEN** the system SHALL return an empty result list with a message indicating no matches found

### Requirement: Normalized search results
The system SHALL normalize results from all sources into a common schema: album artist, album title, release date, source name, source ID, and a list of tracks (each with title, duration in seconds, and optional artist).

#### Scenario: MusicBrainz result normalization
- **WHEN** MusicBrainz returns a release with track lengths in milliseconds
- **THEN** the system SHALL convert durations to seconds (float) in the normalized output

#### Scenario: NetEase result normalization
- **WHEN** NetEase returns album data with `dt` field (duration in milliseconds)
- **THEN** the system SHALL convert `dt` to seconds and extract artist from `ar` array

#### Scenario: Discogs result normalization
- **WHEN** Discogs returns tracklist with duration as string "3:45"
- **THEN** the system SHALL parse the string to seconds (225.0)

### Requirement: Search by artist and album name
The system SHALL accept a free-text query string (e.g., "周杰伦 七里香") and search all configured sources. The query SHALL be passed as-is to each source's search API.

#### Scenario: Chinese language query
- **WHEN** searching for "周杰伦 七里香" (Jay Chou Common Jasmine)
- **THEN** NetEase SHALL return the correct album with 10 tracks and durations

#### Scenario: English language query
- **WHEN** searching for "Pink Floyd The Dark Side of the Moon"
- **THEN** MusicBrainz SHALL return the correct album with track durations

### Requirement: Search by album ID
The system SHALL accept a source name and album ID pair to fetch a specific album directly without search. This enables re-fetching a previously identified album.

#### Scenario: Fetch album by NetEase ID
- **WHEN** fetching album ID 3111188 from NetEase
- **THEN** the system SHALL return the full album metadata with all tracks and durations

#### Scenario: Fetch album by MusicBrainz release ID
- **WHEN** fetching release ID "a1ad1c4d-8363-4f3a-9d72-93757d3c0b37" from MusicBrainz
- **THEN** the system SHALL return the full album metadata with all tracks and durations

### Requirement: Track durations required
The system SHALL only return search results that include track durations. Results without durations SHALL be filtered out or enriched by querying the source for individual track details.

#### Scenario: Discogs result without durations
- **WHEN** Discogs returns a tracklist where some tracks have empty duration fields
- **THEN** the system SHALL query each track individually via the Discogs API to obtain durations, or skip the result if durations cannot be obtained

### Requirement: No authentication for primary sources
The system SHALL NOT require authentication for MusicBrainz, iTunes, Deezer, and NetEase (anonymous access). Discogs SHALL be optional (skipped if no token configured). AcoustID SHALL require an API key but is optional.

#### Scenario: No credentials configured
- **WHEN** no API keys or tokens are configured
- **THEN** the system SHALL search MusicBrainz, iTunes, NetEase, and Deezer, and SHALL skip Discogs

#### Scenario: Discogs token configured
- **WHEN** a Discogs personal access token is configured
- **THEN** the system SHALL include Discogs in the search cascade

### Requirement: Rate limit handling
The system SHALL respect each source's rate limits by implementing appropriate delays between requests. If a source returns a rate limit error (429 or 503), the system SHALL wait and retry with exponential backoff.

#### Scenario: MusicBrainz rate limit
- **WHEN** MusicBrainz returns 503 Service Unavailable
- **THEN** the system SHALL wait 1 second and retry, up to 3 attempts

### Requirement: AcoustID fingerprint identification
The system SHALL optionally support AcoustID/Chromaprint fingerprinting to identify individual tracks within a single-file rip. This is used as a supplementary identification method when text-based search returns ambiguous results.

#### Scenario: Fingerprint identification of first track
- **WHEN** the first 30 seconds of a single-file rip are fingerprinted and submitted to AcoustID
- **THEN** the system SHALL return the identified recording MBID, which can be used to find the corresponding album

#### Scenario: Fingerprint yields no match
- **WHEN** the fingerprint does not match any recording in AcoustID
- **THEN** the system SHALL fall back to text-based search


### Requirement: Interactive search refinement
The system SHALL support interactive query refinement when search results are ambiguous or low-confidence. Users SHALL be able to enter a new search query or specify a direct source ID during the interactive selection process.

#### Scenario: Enter new search query
- **WHEN** the user selects "(e)nter search" at the interactive prompt
- **THEN** the system SHALL prompt for a new query, return a `SearchRefinement` object, and the caller SHALL re-run the search with the new query

#### Scenario: Enter direct source ID
- **WHEN** the user selects "(i)d" at the interactive prompt
- **THEN** the system SHALL prompt for a source:id pair (e.g., "netease:12345"), return a `DirectId` object, and the caller SHALL fetch the specified album directly

#### Scenario: Invalid source ID format
- **WHEN** the user enters an invalid source ID format (missing colon or unknown source)
- **THEN** the system SHALL display an error message and return to the interactive prompt

### Requirement: Progressive search strategy
The system SHALL implement a progressive search strategy with three tiers: Tier 1 (exact ID lookup), Tier 2 (text search with signal extraction), and Tier 3 (ambiguous results with refinement suggestions).

#### Scenario: Direct source ID in query
- **WHEN** the query contains a source:id pair (e.g., "netease:12345")
- **THEN** the system SHALL bypass search and fetch the album directly (Tier 1)

#### Scenario: Ambiguous results with suggestions
- **WHEN** text search returns multiple results with different years or sources
- **THEN** the system SHALL return Tier 3 with refinement suggestions (e.g., add year, specify source, add track name)

#### Scenario: Single strong match
- **WHEN** text search returns exactly one result
- **THEN** the system SHALL return Tier 2 with the single album and no suggestions

### Requirement: Disambiguation signal extraction
The system SHALL extract disambiguation signals from queries and album metadata to help users refine their searches. Signals include year, barcode, catalog number, track name similarity, country hint, and source disambiguation comments.

#### Scenario: Year extraction from query
- **WHEN** the query contains a 4-digit year (e.g., "S.H.E Play 2007")
- **THEN** the system SHALL extract the year and use it for matching and refinement suggestions

#### Scenario: Barcode extraction from query
- **WHEN** the query contains an 8-13 digit barcode
- **THEN** the system SHALL extract the barcode for potential exact matching

#### Scenario: Catalog number extraction from query
- **WHEN** the query contains a catalog number pattern (e.g., "EMI-12345")
- **THEN** the system SHALL extract the catalog number for potential exact matching
