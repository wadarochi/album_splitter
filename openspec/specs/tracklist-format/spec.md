# Tracklist Format

## Purpose

Define a YAML-based project file format for storing album metadata, track listings, detected boundaries, match results, and processing state with support for plain-text input, auto-detection, validation, and multi-format export.

## Requirements

### Requirement: YAML tracklist format
The system SHALL support a YAML-based project file format for storing album metadata, track listings, detected boundaries, match results, and processing state. The format SHALL be human-readable, support comments, and be round-trip compatible (can be written, edited by hand, and re-read without data loss).

#### Scenario: Minimal tracklist (manual input)
- **WHEN** a user creates a tracklist with only album artist and track titles
- **THEN** the YAML SHALL look like:
  ```yaml
  album:
    artist: "周杰伦"
    title: "七里香"
  tracks:
    - title: "我的地盘"
    - title: "七里香"
    - title: "借口"
  ```

#### Scenario: Complete tracklist (after processing)
- **WHEN** the tool has completed detection, search, and matching
- **THEN** the YAML SHALL include all fields:
  ```yaml
  album:
    artist: "周杰伦"
    title: "七里香"
    date: "2004"
    source: "netease"
    source_id: "3111188"
  tracks:
    - title: "我的地盘"
      artist: "周杰伦"
      duration: 232.5
      start: 0.0
      end: 232.5
      confidence: 0.95
    - title: "七里香"
      duration: 299.0
      start: 232.5
      end: 531.5
      confidence: 0.92
  detected_boundaries: [232.5, 531.5]
  cue_file: "album.cue"
  output_dir: "./tracks/"
  ```

### Requirement: Plain text tracklist format
The system SHALL support a simplified plain-text format where each line is one track. Lines starting with # SHALL be treated as comments. The format SHALL be: `Artist - Title` or just `Title` (artist inherits from album-level artist).

#### Scenario: Plain text with artist per track
- **WHEN** parsing a plain text file:
  ```
  # 七里香 tracklist
  周杰伦 - 我的地盘
  周杰伦 - 七里香
  周杰伦 - 借口
  ```
- **THEN** the system SHALL parse 3 tracks with artist "周杰伦" and titles "我的地盘", "七里香", "借口"

#### Scenario: Plain text without artist
- **WHEN** parsing a plain text file:
  ```
  我的地盘
  七里香
  借口
  ```
- **THEN** the system SHALL parse 3 tracks with empty artist (to be filled from album-level metadata)

### Requirement: Format auto-detection
The system SHALL auto-detect the tracklist format based on file extension (.yaml/.yml → YAML, .txt → plain text) or content inspection (valid YAML → YAML, otherwise → plain text).

#### Scenario: Detect YAML by extension
- **WHEN** loading "tracklist.yaml"
- **THEN** the system SHALL parse as YAML format

#### Scenario: Detect plain text by extension
- **WHEN** loading "tracklist.txt"
- **THEN** the system SHALL parse as plain text format

#### Scenario: Detect YAML by content
- **WHEN** loading "tracklist" (no extension) and content starts with "album:"
- **THEN** the system SHALL parse as YAML format

### Requirement: Tracklist to CUE conversion
The system SHALL convert a tracklist (YAML or plain text) into CUE sheet data by combining track titles with detected boundaries and matched timestamps.

#### Scenario: Convert YAML tracklist to CUE
- **WHEN** converting a tracklist with 10 tracks and detected boundaries
- **THEN** the system SHALL produce a CUE sheet with 10 TRACK entries, each with the correct TITLE and INDEX 01 timestamp

### Requirement: Incremental processing state
The YAML tracklist SHALL store processing state to support incremental workflows. The system SHALL be able to resume from any completed step without re-executing previous steps.

#### Scenario: Resume after detection
- **WHEN** a tracklist has `detected_boundaries` filled but `tracks[].start` is empty
- **THEN** the system SHALL skip detection and proceed to matching

#### Scenario: Resume after CUE generation
- **WHEN** a tracklist has `cue_file` filled
- **THEN** the system SHALL skip detection, search, matching, and CUE generation, and proceed directly to splitting

### Requirement: Multi-disc support
The YAML tracklist SHALL support multi-disc albums via a `discs` array. Each disc SHALL have its own file, track list, and boundaries.

#### Scenario: 2-disc album YAML
- **WHEN** creating a tracklist for a 2-disc album
- **THEN** the YAML SHALL look like:
  ```yaml
  album:
    artist: "Artist"
    title: "Double Album"
  discs:
    - file: "disc1.flac"
      tracks:
        - title: "Track 1"
        - title: "Track 2"
    - file: "disc2.flac"
      tracks:
        - title: "Track 3"
        - title: "Track 4"
  ```

### Requirement: Tracklist validation
The system SHALL validate tracklists for structural correctness: at least one track required, track titles non-empty, durations (if present) are positive numbers, boundaries (if present) are non-decreasing.

#### Scenario: Valid tracklist
- **WHEN** validating a tracklist with 10 tracks, all with non-empty titles
- **THEN** the system SHALL return validation success

#### Scenario: Empty tracklist
- **WHEN** validating a tracklist with 0 tracks
- **THEN** the system SHALL return a validation error: "At least one track is required"

#### Scenario: Empty track title
- **WHEN** validating a tracklist where track 3 has an empty title
- **THEN** the system SHALL return a validation error: "Track 3 has an empty title"

### Requirement: Tracklist export
The system SHALL support exporting the tracklist in multiple formats: YAML (default), JSON (--format json), plain text (--format text), and CUE (--format cue).

#### Scenario: Export to JSON
- **WHEN** running `cue-finder export --tracklist project.yaml --format json`
- **THEN** the system SHALL output the tracklist as JSON

#### Scenario: Export to plain text
- **WHEN** running `cue-finder export --tracklist project.yaml --format text`
- **THEN** the system SHALL output the tracklist as plain text (one track per line)
