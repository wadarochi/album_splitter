# Track Matching

## Purpose

Align N silence-detected boundary timestamps to M database-provided track durations using Dynamic Time Warping (DTW) with configurable tolerance, greedy fallback, and boundary refinement.

## Requirements

### Requirement: DTW-based track alignment
The system SHALL align N silence-detected boundary timestamps to M database-provided track durations using Dynamic Time Warping (DTW) with a Sakoe-Chiba band constraint. The tolerance window SHALL be configurable (default ±3.0 seconds).

#### Scenario: Perfect match (N == M, durations align)
- **WHEN** 9 boundaries are detected for a 10-track album and all durations match within ±1s
- **THEN** the system SHALL produce 10 matched tracks with confidence scores ≥ 95%

#### Scenario: Duration mismatch within tolerance
- **WHEN** a detected segment is 3:48 but the database says 3:52 (4s difference, within ±5s tolerance)
- **THEN** the system SHALL match the segment to the track with confidence score adjusted by the deviation

#### Scenario: Segment count mismatch (more segments than tracks)
- **WHEN** 12 boundaries are detected but the album has only 10 tracks
- **THEN** the system SHALL identify the 2 extra segments as low-confidence matches or false positives, and present them for user review

#### Scenario: Segment count mismatch (fewer segments than tracks)
- **WHEN** 7 boundaries are detected but the album has 10 tracks
- **THEN** the system SHALL identify 3 tracks as "unmatched" (possibly gapless transitions) and present them for user review

### Requirement: Greedy matching fallback
The system SHALL use greedy nearest-neighbor matching as a fallback when DTW produces poor results (average confidence below a threshold). Greedy matching assigns each expected boundary to the nearest detected boundary within the tolerance window.

#### Scenario: DTW produces low confidence
- **WHEN** DTW average confidence is below 50%
- **THEN** the system SHALL retry with greedy matching and compare results, presenting the better match to the user

### Requirement: Local boundary refinement
After DTW alignment, the system SHALL refine each boundary by searching within ±gap seconds (configurable, default 30s, matching mp3splt's `-a` behavior) for the frame with the lowest RMS value. This corrects for DTW alignment imprecision.

#### Scenario: Boundary refinement finds better split point
- **WHEN** DTW aligns a boundary to timestamp 210.0s but the lowest-RMS frame within ±2s is at 209.3s
- **THEN** the system SHALL adjust the boundary to 209.3s

#### Scenario: No silence found near expected boundary
- **WHEN** no silence (below threshold) is found within ±gap seconds of the expected boundary
- **THEN** the system SHALL keep the DTW-aligned timestamp and mark the match with reduced confidence

### Requirement: Confidence scoring
The system SHALL assign a confidence score (0.0–1.0) to each matched track based on: duration deviation (closer = higher confidence), boundary refinement success (silence found = higher), and segment count match (N == M = higher).

#### Scenario: High confidence match
- **WHEN** duration deviation < 1s, silence found at boundary, N == M
- **THEN** confidence score SHALL be ≥ 0.95

#### Scenario: Low confidence match
- **WHEN** duration deviation > 5s, no silence found at boundary, N ≠ M
- **THEN** confidence score SHALL be < 0.50

### Requirement: Gapless album detection
The system SHALL detect gapless transitions (where two tracks flow continuously without silence) by checking cross-correlation of audio at expected boundaries. If no silence is found but the expected boundary is strongly indicated by duration matching, the system SHALL mark the transition as "gapless" and use the timestamp from duration accumulation.

#### Scenario: Pink Floyd gapless album
- **WHEN** processing "The Dark Side of the Moon" where several tracks flow continuously
- **THEN** the system SHALL identify gapless transitions and use accumulated duration timestamps, marking them with "gapless" flag and reduced confidence

### Requirement: Internal silence false positive filtering
The system SHALL filter out detected silence regions that do not align with any expected track boundary (within tolerance). These are likely internal silences within a track (e.g., a quiet passage) rather than track boundaries.

#### Scenario: Quiet passage within a track
- **WHEN** a 10-minute track has a 2-second quiet passage at the 5-minute mark
- **THEN** the system SHALL filter out this silence as a false positive if it doesn't align with any expected boundary within ±3s

### Requirement: HTOA (Hidden Track One Audio) detection
The system SHALL detect potential HTOA by checking if there is non-silent audio before the first detected boundary (track 1 start). If audio exists before the first boundary and it's longer than a minimum threshold (default 10s), it SHALL be flagged as a potential hidden track.

#### Scenario: Hidden track before track 1
- **WHEN** a CD rip has 30 seconds of audio before the first detected silence boundary
- **THEN** the system SHALL flag this as a potential HTOA and add it as "Track 0 (Hidden)" in the match results

### Requirement: Match result output
The system SHALL output match results as a list of track objects, each containing: track number, title, artist, start time (seconds), end time (seconds), expected duration (seconds), actual duration (seconds), confidence score (0.0–1.0), and flags (gapless, hidden, unmatched, false_positive).

#### Scenario: Match result for a well-matched album
- **WHEN** a 10-track album is successfully matched
- **THEN** the output SHALL contain 10 track objects with titles, start/end times, and confidence scores ≥ 0.80
