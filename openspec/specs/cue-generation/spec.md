# CUE Generation

## Purpose

Generate, parse, and validate standard CUE sheets from matched track data, with MSF time conversion, multi-disc support, and REM metadata fields.

## Requirements

### Requirement: CUE sheet generation from matched tracks
The system SHALL generate a standard CUE sheet file from matched track data. The CUE sheet SHALL include: PERFORMER (album artist), TITLE (album title), FILE (audio filename with WAVE type), and for each track: TRACK (number, AUDIO type), TITLE (track title), PERFORMER (track artist if different from album artist), INDEX 01 (MM:SS:FF timestamp).

#### Scenario: Generate CUE for 3-track album
- **WHEN** generating a CUE sheet for an album with 3 tracks starting at 0:00, 3:30, and 7:15
- **THEN** the output SHALL be a valid CUE sheet with:
  ```
  PERFORMER "Artist"
  TITLE "Album"
  FILE "album.flac" WAVE
    TRACK 01 AUDIO
      TITLE "Track 1"
      INDEX 01 00:00:00
    TRACK 02 AUDIO
      TITLE "Track 2"
      INDEX 01 03:30:00
    TRACK 03 AUDIO
      TITLE "Track 3"
      INDEX 01 07:15:00
  ```

### Requirement: Sample position to MSF conversion
The system SHALL convert sample positions or floating-point seconds to CUE MSF format (MM:SS:FF) where FF is frames (0–74, at 75 frames per second). The conversion SHALL handle non-44.1kHz sample rates by computing frames_per_second = sample_rate / 75.

#### Scenario: 44.1kHz conversion
- **WHEN** converting 210.5 seconds at 44100 Hz
- **THEN** the system SHALL produce "03:30:37" (3 minutes, 30 seconds, 37 frames)

#### Scenario: 48kHz conversion
- **WHEN** converting 210.5 seconds at 48000 Hz
- **THEN** the system SHALL compute frames based on 48000/75 = 640 samples per frame, producing the correct MSF

#### Scenario: Frame rounding
- **WHEN** the sample position does not align exactly to a frame boundary
- **THEN** the system SHALL round to the nearest frame (not truncate)

### Requirement: CUE sheet parsing
The system SHALL parse existing CUE sheet files to extract track information (titles, performers, INDEX timestamps). This enables editing and re-generation of CUE sheets.

#### Scenario: Parse valid CUE sheet
- **WHEN** parsing a CUE sheet with 10 tracks
- **THEN** the system SHALL return a list of 10 track objects with titles, performers, and start times in seconds

#### Scenario: Parse CUE with REM comments
- **WHEN** parsing a CUE sheet with REM GENRE, REM DATE, REM COMMENT fields
- **THEN** the system SHALL extract these as optional metadata fields

### Requirement: CUE sheet validation
The system SHALL validate generated CUE sheets for structural correctness: sequential track numbers, required INDEX 01 for each track, first track starts at 00:00:00, timestamps are non-decreasing.

#### Scenario: Valid CUE sheet
- **WHEN** validating a well-formed CUE sheet
- **THEN** the system SHALL return validation success with no errors

#### Scenario: CUE with missing INDEX 01
- **WHEN** validating a CUE sheet where track 3 has no INDEX 01
- **THEN** the system SHALL return a validation error: "Track 03 missing required INDEX 01"

#### Scenario: CUE with non-sequential tracks
- **WHEN** validating a CUE sheet with tracks 01, 02, 04 (missing 03)
- **THEN** the system SHALL return a validation error: "Track numbers must be sequential"

### Requirement: Multi-disc CUE support
The system SHALL support generating CUE sheets for multi-disc albums. Each disc SHALL be a separate FILE entry in the CUE sheet, with track numbers continuing sequentially across discs.

#### Scenario: 2-disc album
- **WHEN** generating a CUE for a 2-disc album with 10 tracks per disc
- **THEN** the CUE SHALL contain 2 FILE entries and 20 TRACK entries (01–20)

### Requirement: REM metadata fields
The system SHALL optionally include REM fields in the generated CUE sheet for additional metadata: REM DATE (release year), REM GENRE (genre), REM DISCID (computed disc ID if available), REM COMMENT (arbitrary comments).

#### Scenario: CUE with REM metadata
- **WHEN** generating a CUE sheet with metadata including date "2004" and genre "Pop"
- **THEN** the CUE SHALL include:
  ```
  REM DATE "2004"
  REM GENRE "Pop"
  ```

### Requirement: File path handling in CUE
The system SHALL use the audio file's basename (not full path) in the CUE FILE directive. The CUE file SHALL be written to the same directory as the audio file by default, or to a user-specified output path.

#### Scenario: CUE filename relative to audio
- **WHEN** generating a CUE for "F:\music\album.flac"
- **THEN** the FILE directive SHALL contain "album.flac" (basename only), and the CUE file SHALL be written to "F:\music\album.cue" by default
