# Beets Tagging

## Purpose

Tag split audio files with metadata from CUE sheets using cuetag, mutagen fallback, and optional beets import for advanced metadata completion.

## Requirements

### Requirement: cuetag integration
The system SHALL invoke the `cuetag` command-line tool to write CUE sheet metadata (track titles, performers) to split audio files' embedded tags (Vorbis Comments for FLAC, ID3 for MP3, APEv2 for APE).

#### Scenario: Tag FLAC files from CUE
- **WHEN** tagging 10 split FLAC files using "album.cue"
- **THEN** the system SHALL invoke `cuetag album.cue ./tracks/*.flac` and each file SHALL have TITLE, ARTIST, ALBUM, TRACKNUMBER tags written

#### Scenario: cuetag not installed
- **WHEN** cuetag is not found in PATH
- **THEN** the system SHALL fall back to writing tags via Python mutagen library directly from CUE data

### Requirement: beets import integration
The system SHALL invoke `beet import` on the split files directory to trigger beets' autotagger. The system SHALL pass appropriate flags: `-s` for singleton mode (individual tracks) or default album mode (grouped release).

#### Scenario: Album mode import
- **WHEN** importing a split 10-track album with `--beets-mode album`
- **THEN** the system SHALL invoke `beet import ./tracks/` and beets SHALL attempt to match the album to MusicBrainz

#### Scenario: Singleton mode import
- **WHEN** importing split tracks with `--beets-mode singleton`
- **THEN** the system SHALL invoke `beet import -s ./tracks/*.flac` and beets SHALL match each track individually

### Requirement: beets plugin configuration
The system SHALL recommend (and optionally verify) that beets is configured with the following plugins: chroma (AcoustID fingerprinting), musicbrainz (metadata source), discogs (fallback metadata), fromfilename (filename-based fallback).

#### Scenario: Verify beets plugins
- **WHEN** beets integration is invoked
- **THEN** the system SHALL check beets config for required plugins and warn if any are missing

#### Scenario: chroma plugin auto-fingerprints
- **WHEN** beets import runs with chroma plugin enabled
- **THEN** beets SHALL fingerprint each split file via AcoustID and match to MusicBrainz recordings, even if CUE tags are incomplete

### Requirement: beets config path
The system SHALL accept a custom beets config file path via --beets-config option. If not specified, the system SHALL use beets' default config location.

#### Scenario: Custom beets config
- **WHEN** --beets-config "$HOME/.config/beets/config.yaml" is specified
- **THEN** the system SHALL invoke `beet -c "$HOME/.config/beets/config.yaml" import ./tracks/`

### Requirement: Non-destructive tagging
The system SHALL NOT delete or overwrite the original single-file audio rip. All splitting and tagging operations SHALL produce new files in the output directory, leaving the source file untouched.

#### Scenario: Original file preserved
- **WHEN** splitting and tagging "album.flac" into ./tracks/
- **THEN** "album.flac" SHALL remain unmodified in its original location

### Requirement: Tag verification
After beets import, the system SHALL verify that each output file has the expected tags (at minimum: title, artist, album, tracknumber) by reading them back via mutagen.

#### Scenario: All tags present
- **WHEN** verifying tags on 10 split FLAC files after beets import
- **THEN** each file SHALL have non-empty TITLE, ARTIST, ALBUM, TRACKNUMBER tags

#### Scenario: Missing tags reported
- **WHEN** a split file is missing the ARTIST tag after beets import
- **THEN** the system SHALL report the file and missing tag as a warning

### Requirement: Optional beets skip
The system SHALL allow skipping beets integration entirely via --no-beets flag. In this case, only cuetag (or mutagen fallback) SHALL be used for tagging.

#### Scenario: Skip beets, use cuetag only
- **WHEN** --no-beets is specified
- **THEN** the system SHALL only invoke cuetag (or mutagen fallback) and SHALL NOT invoke `beet import`

### Requirement: beets not installed handling
The system SHALL gracefully handle the case where beets is not installed. If beets is not found in PATH, the system SHALL warn the user and continue with cuetag/mutagen tagging only.

#### Scenario: beets not installed
- **WHEN** beets is not found in PATH and --no-beets is not specified
- **THEN** the system SHALL print a warning, skip beets import, and continue with cuetag/mutagen tagging
