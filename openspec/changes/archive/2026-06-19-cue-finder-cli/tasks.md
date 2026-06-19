## 1. Project Setup

- [x] 1.1 Create `pyproject.toml` with all dependencies (typer, rich, textual, questionary, musicbrainzngs, python3-discogs-client, deezer-python, pyncm, pyacoustid, pyyaml, mutagen, soundfile, numpy)
- [x] 1.2 Create package structure: `cue_finder/__init__.py`, `cue_finder/cli.py`, `cue_finder/core/`, `cue_finder/tui/`, `cue_finder/backends/`
- [x] 1.3 Create `cue_finder/core/__init__.py`, `cue_finder/tui/__init__.py`, `cue_finder/backends/__init__.py`
- [x] 1.4 Configure `pyproject.toml` entry point: `cue-finder = "cue_finder.cli:app"`
- [x] 1.5 Set up `tests/` directory with `conftest.py` and test fixtures (sample audio files)

## 2. Silence Detection Module (`core/silence.py`)

- [x] 2.1 Create `SilenceDetector` class wrapping `slicer2.Slicer` and `slicer2.get_rms`
- [x] 2.2 Implement `detect_boundaries(audio_path, **params) -> list[float]` returning boundary timestamps in seconds
- [x] 2.3 Implement streaming RMS calculation by adapting `build_rms_list_from_file` from `gui/slicing_tasks.py`
- [x] 2.4 Add parameter validation (min_length >= min_interval >= hop_size, max_sil_kept >= hop_size)
- [x] 2.5 Handle mono/stereo downmix for RMS calculation without affecting output
- [x] 2.6 Write unit tests: clear silence gaps, gapless album, short file, leading/trailing silence, invalid params

## 3. Metadata Search Module (`core/search.py`)

- [x] 3.1 Define `AlbumInfo` and `TrackInfo` dataclasses (normalized schema: artist, title, date, source, source_id, tracks[{title, duration_sec, artist}])
- [x] 3.2 Implement MusicBrainz search adapter using `musicbrainzngs` (search_releases, get_release_by_id with recordings+media includes)
- [x] 3.3 Implement iTunes search adapter using `requests` (no auth, search endpoint + lookup endpoint for tracks)
- [x] 3.4 Implement NetEase search adapter using `pyncm` (apis.cloudsearch.GetSearchResult, apis.album.GetAlbumInfo, extract `dt` field for durations)
- [x] 3.5 Implement Discogs search adapter using `python3-discogs-client` (requires token, parse duration strings "3:45" to seconds)
- [x] 3.6 Implement Deezer search adapter using `deezer-python` (no auth, search_albums + get_tracks)
- [x] 3.7 Implement GnuDB search adapter using CDDB protocol (fallback for legacy CDs)
- [x] 3.8 Implement AcoustID fingerprint adapter using `pyacoustid` (fingerprint_file + lookup, return recording MBIDs)
- [x] 3.9 Implement cascading fallback orchestrator: try sources in order, return first successful results
- [x] 3.10 Implement rate limit handling: per-source delays, 429/503 retry with exponential backoff (max 3 retries)
- [x] 3.11 Implement source availability detection: skip sources without required credentials/binaries
- [x] 3.12 Write unit tests with mocked API responses for each source adapter
- [x] 3.13 Write integration tests (marked @pytest.mark.integration) for live API queries

## 4. Track Matching Module (`core/match.py`)

- [x] 4.1 Implement `TrackMatcher` class with configurable tolerance (default ±3.0s)
- [x] 4.2 Implement DTW alignment using `librosa.sequence.dtw` with Sakoe-Chiba band constraint
- [x] 4.3 Implement greedy nearest-neighbor matching as fallback algorithm
- [x] 4.4 Implement local boundary refinement: search ±gap seconds (default 30s) for lowest-RMS frame near each expected boundary
- [x] 4.5 Implement confidence scoring: duration deviation + boundary refinement success + segment count match
- [x] 4.6 Implement gapless transition detection: cross-correlation at expected boundaries
- [x] 4.7 Implement internal silence false positive filtering: remove detected silences not near any expected boundary
- [x] 4.8 Implement HTOA detection: check for non-silent audio before first boundary
- [x] 4.9 Implement match result output: list of TrackMatch objects (number, title, artist, start, end, expected_duration, actual_duration, confidence, flags)
- [x] 4.10 Write unit tests: perfect match, duration mismatch, N≠M (more segments), N≠M (fewer segments), gapless album, false positive filtering, HTOA

## 5. CUE Generation Module (`core/cue.py`)

- [x] 5.1 Implement `samples_to_msf(samples, sample_rate) -> str` conversion (75 frames/second, round to nearest frame)
- [x] 5.2 Implement `seconds_to_msf(seconds, sample_rate) -> str` conversion
- [x] 5.3 Implement `msf_to_seconds(msf: str) -> float` reverse conversion
- [x] 5.4 Implement `generate_cue(album_info, matched_tracks, audio_filename) -> str` producing full CUE sheet text
- [x] 5.5 Implement CUE sheet writing to file with proper encoding (UTF-8 with BOM for Windows compatibility)
- [x] 5.6 Implement `parse_cue(cue_path) -> CueSheet` parsing existing CUE files (FILE, TRACK, INDEX, PERFORMER, TITLE, REM)
- [x] 5.7 Implement `validate_cue(cue_text) -> list[str]` validation (sequential tracks, required INDEX 01, non-decreasing timestamps, first track at 00:00:00)
- [x] 5.8 Implement multi-disc CUE support (multiple FILE entries, sequential track numbers)
- [x] 5.9 Implement REM metadata fields (REM DATE, REM GENRE, REM COMMENT)
- [x] 5.10 Write unit tests: MSF conversion (44.1kHz, 48kHz), CUE generation, CUE parsing, validation (valid/invalid), multi-disc

## 6. Audio Splitting Module (`core/split.py` + `backends/`)

- [x] 6.1 Create `Splitter` class with format auto-detection from file extension
- [x] 6.2 Implement `split(audio_path, cue_path_or_timestamps, output_dir, format, name_template) -> list[str]`
- [x] 6.3 Implement backend auto-detection: check PATH for flac-tracksplit, flacsplt, shnsplit, mac.exe, ffmpeg
- [x] 6.4 Implement `backends/flac_splitter.py`: flac-tracksplit → flacsplt → shntool fallback chain
- [x] 6.5 Implement `backends/wav_splitter.py`: Python `wave` module, sample-accurate, streaming write (65536-frame blocks)
- [x] 6.6 Implement `backends/ape_splitter.py`: ffmpeg decode (primary) → mac.exe fallback → WAV split → optional FLAC re-encode via soundfile
- [x] 6.7 Implement output file naming: default `{track:02d} - {title}.{format}`, configurable via name_template
- [x] 6.8 Implement output format conversion (FLAC↔WAV, APE→FLAC)
- [x] 6.9 Implement streaming write for large files (block-by-block, max 100MB memory)
- [x] 6.10 Implement backend status reporting (which binaries found, which will be used)
- [x] 6.11 Write unit tests: WAV splitting (wave module), FLAC splitting (mocked backends), APE decode (mocked mac.exe), naming patterns, format conversion

## 7. Beets Tagging Module (`core/tag.py`)

- [x] 7.1 Implement `tag_tracks(track_dir, cue_path, beets_config=None, use_beets=True) -> TagResult`
- [x] 7.2 Implement cuetag invocation via subprocess: `cuetag <cue> <tracks_glob>`
- [x] 7.3 Implement mutagen fallback for tagging when cuetag is not available (write Vorbis Comments for FLAC, ID3 for MP3)
- [x] 7.4 Implement beets import invocation: `beet import` (album mode) or `beet import -s` (singleton mode)
- [x] 7.5 Implement beets config path handling (--beets-config flag)
- [x] 7.6 Implement beets plugin verification: check config for chroma, musicbrainz, discogs, fromfilename
- [x] 7.7 Implement tag verification: read back tags via mutagen after import, verify title/artist/album/tracknumber present
- [x] 7.8 Implement --no-beets flag (cuetag/mutagen only)
- [x] 7.9 Implement graceful handling when beets is not installed (warn + continue with cuetag/mutagen)
- [x] 7.10 Write unit tests: cuetag invocation (mocked subprocess), mutagen fallback, tag verification, beets not installed

## 8. Tracklist Format Module (`core/tracklist.py`)

- [x] 8.1 Define `Tracklist` dataclass (album info, tracks, detected_boundaries, cue_file, output_dir)
- [x] 8.2 Implement YAML serialization/deserialization using pyyaml
- [x] 8.3 Implement plain text parsing: `Artist - Title` or `Title` per line, # comments
- [x] 8.4 Implement format auto-detection (by extension, then by content)
- [x] 8.5 Implement tracklist validation: at least 1 track, non-empty titles, positive durations, non-decreasing boundaries
- [x] 8.6 Implement incremental processing state: detected_boundaries, matched tracks, cue_file, output_dir fields
- [x] 8.7 Implement multi-disc support (discs array with per-disc file/tracks/boundaries)
- [x] 8.8 Implement export to JSON, plain text, and CUE formats
- [x] 8.9 Write unit tests: YAML round-trip, plain text parsing, validation, multi-disc, export formats

## 9. CLI Interface (`cli.py`)

- [x] 9.1 Create Typer app with subcommands: search, detect, generate, split, tag, run, tui
- [x] 9.2 Implement `search` subcommand: query string, --source filter, --json output, Rich table output
- [x] 9.3 Implement `detect` subcommand: -i input, --threshold, --min-length, --min-interval, --hop-size, --max-sil-kept, -o output JSON
- [x] 9.4 Implement `generate` subcommand: -i input, --tracklist or --search, -o CUE output
- [x] 9.5 Implement `split` subcommand: -i input, -c CUE or --timestamps, -o output dir, --format, --name-template
- [x] 9.6 Implement `tag` subcommand: -d tracks dir, -c CUE, --beets/--no-beets, --beets-config, --beets-mode
- [x] 9.7 Implement `run` subcommand: full pipeline with all options from detect+search+generate+split+tag
- [x] 9.8 Implement `tui` subcommand: launch Textual TUI
- [x] 9.9 Implement TTY auto-detection: launch TUI if TTY and no subcommand, print help if no TTY
- [x] 9.10 Implement global options: --verbose/-v, --quiet/-q, --interactive/--no-interactive
- [x] 9.11 Implement Rich progress bars for long-running operations (detection, splitting, tagging)
- [x] 9.12 Implement Rich error panels for error messages
- [x] 9.13 Implement exit codes: 0 success, 1 partial failure, 2 complete failure, 3 invalid args, 4 missing deps
- [x] 9.14 Implement logging configuration (DEBUG/INFO/WARNING based on -v/-q)
- [x] 9.15 Write CLI integration tests using Typer's CliRunner

## 10. TUI Interface (`tui/`)

- [x] 10.1 Create `tui/app.py`: Textual App subclass with CSS styling
- [x] 10.2 Implement search view: Input widget for query, DataTable for results, source filter
- [x] 10.3 Implement track list view: DataTable with columns (#, Title, Expected, Detected, Deviation, Confidence, Flags)
- [x] 10.4 Implement track editing: rename, reorder, merge, split, delete, manual boundary adjustment
- [x] 10.5 Implement CUE preview view: Static widget with live-updating CUE text
- [x] 10.6 Implement progress view: ProgressBar widget for detection/splitting/tagging
- [x] 10.7 Implement keybindings: Enter (confirm), e (edit), r (re-detect), q (quit), s (search)
- [x] 10.8 Implement album selection flow: search → select album → populate track list → review → run
- [x] 10.9 Implement file picker for audio file selection
- [x] 10.10 Write TUI smoke tests (Textual test pilot / pilot mode)

## 11. Skill Packaging

- [x] 11.1 Create `skills/cue-finder/SKILL.md` with skill description, trigger phrases, and usage examples
- [x] 11.2 Document natural language invocation patterns ("用 cue-finder 拆分这个CDImage")
- [x] 11.3 Document non-interactive CLI usage for AI agent invocation
- [x] 11.4 Create example workflows in SKILL.md (full pipeline, search only, split only)

## 12. Documentation

- [x] 12.1 Create `README.md` with installation instructions, quick start, and architecture overview
- [x] 12.2 Document external binary dependencies and installation for Windows/Linux/macOS
- [x] 12.3 Document YAML tracklist format with examples
- [x] 12.4 Document all CLI subcommands and options
- [x] 12.5 Document TUI usage with screenshots
- [x] 12.6 Document beets integration setup
- [x] 12.7 Create `docs/troubleshooting.md` for common issues (missing binaries, API rate limits, match failures)

## 13. Integration Testing

- [x] 13.1 Create test fixture: synthetic 3-track WAV file with clear silence gaps
- [x] 13.2 Test full pipeline: detect → search (mocked) → match → generate CUE → split → tag (mocked)
- [x] 13.3 Test FLAC splitting with real flac.exe (if available in test env)
- [x] 13.4 Test APE decoding with real mac.exe (if available in test env)
- [x] 13.5 Test multi-source search fallback (mock some sources as unavailable)
- [x] 13.6 Test incremental workflow: detect → save tracklist → resume → split
- [x] 13.7 Test TTY auto-detection (mock isatty)
- [x] 13.8 Test error recovery: missing binary, API timeout, invalid CUE, corrupt audio
