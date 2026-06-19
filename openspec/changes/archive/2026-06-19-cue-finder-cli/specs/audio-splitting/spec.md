## ADDED Requirements

### Requirement: Format-specific splitting backends
The system SHALL select the splitting backend based on input audio format (detected from file extension): FLAC uses flac-tracksplit → flacsplt → shntool fallback chain; WAV uses Python wave module; APE uses mac.exe decode → WAV split → optional FLAC re-encode.

#### Scenario: FLAC splitting with flac-tracksplit available
- **WHEN** splitting a FLAC file and flac-tracksplit binary is found in PATH
- **THEN** the system SHALL use flac-tracksplit for frame-level lossless splitting

#### Scenario: FLAC splitting fallback to flacsplt
- **WHEN** splitting a FLAC file, flac-tracksplit is not available, but flacsplt is found
- **THEN** the system SHALL use flacsplt for frame-level lossless splitting

#### Scenario: FLAC splitting fallback to shntool
- **WHEN** splitting a FLAC file and neither flac-tracksplit nor flacsplt is available, but shntool + flac.exe are found
- **THEN** the system SHALL use shntool with flac helper (decodes and re-encodes, but sample-accurate)

#### Scenario: WAV splitting with Python wave module
- **WHEN** splitting a WAV file
- **THEN** the system SHALL use Python's built-in wave module for sample-accurate splitting with no external dependencies

#### Scenario: APE splitting requires mac.exe
- **WHEN** splitting an APE file
- **THEN** the system SHALL decode APE to temporary WAV using mac.exe, split the WAV, then optionally re-encode each track to FLAC

#### Scenario: No suitable backend available
- **WHEN** no splitting backend is available for the input format
- **THEN** the system SHALL raise a clear error message listing required binaries and installation instructions

### Requirement: CUE-driven splitting
The system SHALL accept a CUE sheet file as the splitting directive. The CUE file's INDEX 01 timestamps SHALL determine the split points. The FILE directive in the CUE SHALL specify the input audio file (relative to CUE file location or overridden by command-line argument).

#### Scenario: Split using CUE sheet
- **WHEN** splitting "album.flac" using "album.cue" with 10 tracks
- **THEN** the system SHALL produce 10 output files, one per track, with boundaries matching CUE INDEX 01 timestamps

#### Scenario: CUE FILE directive override
- **WHEN** the CUE file specifies FILE "oldname.flac" but the user provides --input "album.flac"
- **THEN** the system SHALL use the user-specified file path, ignoring the CUE's FILE directive

### Requirement: Timestamp-driven splitting (without CUE)
The system SHALL also accept a list of timestamps (in seconds) directly, without requiring a CUE file. This enables splitting directly from silence detection output.

#### Scenario: Split using timestamp list
- **WHEN** splitting with timestamps [0.0, 210.0, 435.0, 680.0]
- **THEN** the system SHALL produce 3 output files: [0.0–210.0], [210.0–435.0], [435.0–680.0]

### Requirement: Output file naming
The system SHALL name output files using the pattern `{track_number:02d} - {track_title}.{format}` by default (e.g., "01 - My Song.flac"). The naming pattern SHALL be configurable via --name-template option.

#### Scenario: Default naming
- **WHEN** splitting a 3-track album with titles "Song A", "Song B", "Song C"
- **THEN** output files SHALL be "01 - Song A.flac", "02 - Song B.flac", "03 - Song C.flac"

#### Scenario: Custom naming template
- **WHEN** splitting with --name-template "{artist} - {album} - {track:02d} - {title}"
- **THEN** output files SHALL follow the custom pattern

### Requirement: Output format conversion
The system SHALL support optional output format conversion during splitting. Supported output formats: FLAC, WAV. If the output format differs from the input format, the system SHALL transcode (lossless to lossless only).

#### Scenario: APE to FLAC conversion
- **WHEN** splitting an APE file with --format flac
- **THEN** the system SHALL decode APE to WAV, split, and encode each track as FLAC

#### Scenario: WAV to FLAC conversion
- **WHEN** splitting a WAV file with --format flac
- **THEN** the system SHALL split WAV and encode each track as FLAC

#### Scenario: Same format (no conversion)
- **WHEN** splitting a FLAC file with --format flac (or no --format specified)
- **THEN** the system SHALL output FLAC files without format conversion

### Requirement: Lossless splitting guarantee
The system SHALL NOT perform lossy re-encoding. All splitting operations SHALL preserve audio quality: FLAC frame-level copy (flac-tracksplit/flacsplt), sample-accurate copy (wave module/shntool), or lossless decode-encode (APE→WAV→FLAC, all lossless codecs).

#### Scenario: FLAC frame-level lossless
- **WHEN** splitting FLAC with flac-tracksplit
- **THEN** the output FLAC files SHALL contain identical audio samples to the source, with no re-encoding of audio data

#### Scenario: APE decode is lossless
- **WHEN** decoding APE to WAV using mac.exe
- **THEN** the WAV file SHALL contain bit-identical samples to the original APE audio

### Requirement: Streaming write for large files
The system SHALL write output files in streaming mode (block-by-block) without loading entire tracks into memory. Block size SHALL be configurable (default 65536 frames).

#### Scenario: Splitting a 90-minute file into 10 tracks
- **WHEN** splitting a 90-minute FLAC file into 10 tracks
- **THEN** peak memory usage during splitting SHALL NOT exceed 100MB

### Requirement: Binary auto-detection
The system SHALL auto-detect available splitting backends at startup by checking for binaries in PATH. The system SHALL report which backends are available and which will be used for each format.

#### Scenario: Backend status report
- **WHEN** the tool starts and detects available binaries
- **THEN** the system SHALL print a status table showing: flac-tracksplit (found/not found), flacsplt (found/not found), shntool (found/not found), mac.exe (found/not found), ffmpeg (found/not found)

#### Scenario: Graceful degradation
- **WHEN** flac-tracksplit is not available but flacsplt is
- **THEN** the system SHALL use flacsplt without error, and SHALL only warn if no backend is available for a requested format
