## ADDED Requirements

### Requirement: Silence detection from audio file
The system SHALL accept an audio file path (FLAC, WAV, APE, or any format supported by libsndfile) and produce a list of track boundary timestamps in seconds. The detection SHALL use RMS-based silence analysis with configurable parameters: threshold (dB, default -40), min_length (ms, default 5000), min_interval (ms, default 300), hop_size (ms, default 10), max_sil_kept (ms, default 500).

#### Scenario: Single file with clear silence gaps
- **WHEN** a 30-minute FLAC file with 10 tracks separated by 2-second silence gaps is processed
- **THEN** the system SHALL return 9 boundary timestamps (between 10 tracks) accurate to within ±hop_size milliseconds

#### Scenario: File with no detectable silence
- **WHEN** a gapless album (e.g., DJ mix) with no silence longer than min_interval is processed
- **THEN** the system SHALL return an empty boundary list, indicating no split points found

#### Scenario: Very short audio file
- **WHEN** an audio file shorter than min_length is processed
- **THEN** the system SHALL return an empty boundary list (single track, no splits)

#### Scenario: File with leading and trailing silence
- **WHEN** an audio file has 5 seconds of silence at the start and 3 seconds at the end
- **THEN** the system SHALL NOT produce boundaries for leading/trailing silence; the first boundary SHALL correspond to the first inter-track gap

### Requirement: Streaming audio processing
The system SHALL process audio files in streaming mode without loading the entire file into memory. The RMS calculation SHALL read audio in configurable block sizes (default 131072 frames) and process incrementally.

#### Scenario: Large FLAC file (90 minutes)
- **WHEN** a 90-minute stereo FLAC file (44.1kHz, 16-bit) is processed
- **THEN** peak memory usage SHALL NOT exceed 100MB regardless of file size

#### Scenario: Mono vs stereo handling
- **WHEN** a stereo audio file is processed
- **THEN** the system SHALL downmix to mono for RMS calculation without affecting the output audio quality

### Requirement: Configurable detection parameters
The system SHALL expose all silence detection parameters as configurable options with sensible defaults. Parameters SHALL be validated before processing begins.

#### Scenario: Invalid parameter combination
- **WHEN** min_length < min_interval is specified
- **THEN** the system SHALL raise a ValueError with a descriptive message before processing begins

#### Scenario: Custom threshold for noisy recordings
- **WHEN** threshold is set to -30 dB for a noisy vinyl recording
- **THEN** the system SHALL use the less strict threshold, detecting fewer but more certain silence regions

### Requirement: Boundary output format
The system SHALL output boundaries as a list of floating-point timestamps in seconds, where each timestamp represents the approximate start of a silence region that separates two tracks. The first track is implicitly assumed to start at 0.0 seconds.

#### Scenario: Boundary list for 3-track album
- **WHEN** a 3-track album with boundaries at 3:30 and 7:15 is processed
- **THEN** the system SHALL return `[210.0, 435.0]` (2 boundaries for 3 tracks)

### Requirement: Reuse existing slicer2 algorithm
The system SHALL reuse the `Slicer` class and `get_rms` function from the existing `audio-slicer` project's `slicer2.py`. The algorithm SHALL NOT be reimplemented from scratch.

#### Scenario: Algorithm consistency with audio-slicer
- **WHEN** the same audio file and parameters are processed by both audio-slicer's `Slicer.slice_ranges()` and this tool's silence detection
- **THEN** the boundary timestamps SHALL match exactly (same algorithm, same RMS calculation)
