## ADDED Requirements

### Requirement: Non-interactive CLI mode
The system SHALL provide a fully non-interactive command-line interface using Typer with subcommands: search, detect, generate, split, tag, run, tui. All options SHALL be specifiable via command-line flags and arguments without any interactive prompts.

#### Scenario: Full pipeline non-interactive
- **WHEN** running `cue-finder run -i album.flac --search "Artist Album" --output ./tracks/ --format flac`
- **THEN** the system SHALL execute the entire pipeline (detect → search → match → generate CUE → split → tag) without any user interaction

#### Scenario: Individual subcommand execution
- **WHEN** running `cue-finder detect -i album.flac --threshold -35 -o boundaries.json`
- **THEN** the system SHALL execute only the silence detection step and output boundaries to a JSON file

### Requirement: Subcommand: search
The `search` subcommand SHALL accept a query string and optional source filter, and print normalized search results as a Rich-formatted table (interactive) or JSON (non-interactive with --json flag).

#### Scenario: Search with table output
- **WHEN** running `cue-finder search "周杰伦 七里香"`
- **THEN** the system SHALL print a table with columns: #, Album, Artist, Year, Tracks, Source

#### Scenario: Search with JSON output
- **WHEN** running `cue-finder search "周杰伦 七里香" --json`
- **THEN** the system SHALL print a JSON array of normalized album objects

### Requirement: Subcommand: detect
The `detect` subcommand SHALL accept an audio file path and silence detection parameters, and output boundary timestamps as JSON or YAML.

#### Scenario: Detect with default parameters
- **WHEN** running `cue-finder detect -i album.flac`
- **THEN** the system SHALL output a JSON array of boundary timestamps in seconds

#### Scenario: Detect with custom parameters
- **WHEN** running `cue-finder detect -i album.flac --threshold -30 --min-length 3000`
- **THEN** the system SHALL use the custom parameters for silence detection

### Requirement: Subcommand: generate
The `generate` subcommand SHALL accept an audio file path and a tracklist file (YAML or plain text), search for album metadata if not provided in the tracklist, match boundaries, and output a CUE sheet.

#### Scenario: Generate CUE from tracklist
- **WHEN** running `cue-finder generate -i album.flac --tracklist tracklist.yaml -o album.cue`
- **THEN** the system SHALL detect boundaries, match with tracklist, and write a CUE sheet

#### Scenario: Generate CUE with auto-search
- **WHEN** running `cue-finder generate -i album.flac --search "Artist Album" -o album.cue`
- **THEN** the system SHALL search for metadata, detect boundaries, match, and write a CUE sheet

### Requirement: Subcommand: split
The `split` subcommand SHALL accept an audio file path and either a CUE file or a timestamp list, and produce split audio files in the output directory.

#### Scenario: Split using CUE
- **WHEN** running `cue-finder split -i album.flac -c album.cue -o ./tracks/ --format flac`
- **THEN** the system SHALL split the audio into individual track files

#### Scenario: Split using timestamps
- **WHEN** running `cue-finder split -i album.flac --timestamps "0,210,435,680" -o ./tracks/`
- **THEN** the system SHALL split at the specified timestamps

### Requirement: Subcommand: tag
The `tag` subcommand SHALL accept a directory of split audio files and a CUE file, and invoke cuetag + beets import for metadata tagging.

#### Scenario: Tag with beets
- **WHEN** running `cue-finder tag -d ./tracks/ -c album.cue --beets`
- **THEN** the system SHALL invoke cuetag and beet import on the tracks directory

### Requirement: Subcommand: run
The `run` subcommand SHALL execute the full pipeline: detect → search → match → generate CUE → split → tag. It SHALL accept all parameters needed for each step.

#### Scenario: Full pipeline with search
- **WHEN** running `cue-finder run -i album.flac --search "Artist Album" -o ./tracks/`
- **THEN** the system SHALL execute all steps and produce tagged split files

#### Scenario: Full pipeline with tracklist
- **WHEN** running `cue-finder run -i album.flac --tracklist tracklist.yaml -o ./tracks/`
- **THEN** the system SHALL use the tracklist instead of searching, and execute all other steps

### Requirement: Subcommand: tui
The `tui` subcommand SHALL launch the Textual-based full-screen interactive TUI. The TUI SHALL provide: album search, search results selection, track list editing, CUE preview, and pipeline execution with progress indicators.

#### Scenario: Launch TUI
- **WHEN** running `cue-finder tui`
- **THEN** the system SHALL launch a full-screen Textual application

### Requirement: TTY auto-detection
The system SHALL auto-detect whether stdin is a TTY. If TTY and no subcommand is given, the system SHALL launch the TUI. If not TTY (piped/scripted), the system SHALL require explicit subcommands.

#### Scenario: Terminal launch without subcommand
- **WHEN** running `cue-finder` in a terminal (TTY present) without a subcommand
- **THEN** the system SHALL launch the TUI automatically

#### Scenario: Piped input requires subcommand
- **WHEN** running `cue-finder` in a script (no TTY) without a subcommand
- **THEN** the system SHALL print help text and exit with non-zero status

### Requirement: Rich-formatted output
In non-interactive mode, the system SHALL use Rich for all terminal output: tables for search results, progress bars for long-running operations, colored text for status messages, and panels for error messages.

#### Scenario: Progress bar during detection
- **WHEN** silence detection is running on a large file
- **THEN** the system SHALL display a Rich progress bar showing elapsed time and estimated completion

#### Scenario: Error in Rich panel
- **WHEN** an error occurs during processing
- **THEN** the system SHALL display the error in a red-bordered Rich panel with the error message and suggested fix

### Requirement: TUI search interface
The TUI SHALL provide a search input field and a DataTable widget for displaying search results. Selecting a result SHALL populate the track list view.

#### Scenario: Search in TUI
- **WHEN** the user types "周杰伦 七里香" in the search field and presses Enter
- **THEN** the DataTable SHALL populate with search results from all configured sources

#### Scenario: Select album in TUI
- **WHEN** the user selects an album from the search results
- **THEN** the track list view SHALL populate with the album's tracks, showing expected vs detected durations and confidence scores

### Requirement: TUI track editing
The TUI SHALL allow the user to edit the track list: rename tracks, reorder tracks, merge adjacent segments, split a segment into two, delete a segment, and manually adjust boundary timestamps.

#### Scenario: Rename a track
- **WHEN** the user selects a track and types a new title
- **THEN** the track title SHALL be updated in the track list and reflected in the CUE preview

#### Scenario: Manual boundary adjustment
- **WHEN** the user selects a boundary and enters a new timestamp
- **THEN** the boundary SHALL be updated, confidence recalculated, and CUE preview updated

### Requirement: TUI CUE preview
The TUI SHALL display a live preview of the CUE sheet that would be generated from the current track list and boundaries. The preview SHALL update in real-time as the user edits tracks or boundaries.

#### Scenario: CUE preview updates on edit
- **WHEN** the user renames track 3 from "Unknown" to "My Song"
- **THEN** the CUE preview SHALL immediately update the TRACK 03 TITLE line to show "My Song"

### Requirement: TUI pipeline execution
The TUI SHALL provide a "Run" action that executes the full pipeline (split + tag) with a progress indicator. The user SHALL be able to review the CUE sheet before executing.

#### Scenario: Execute pipeline from TUI
- **WHEN** the user presses the "Run" button after reviewing the CUE preview
- **THEN** the TUI SHALL execute splitting and tagging, showing progress bars for each step

### Requirement: Exit codes
The system SHALL return appropriate exit codes: 0 for success, 1 for partial failure (some tracks processed), 2 for complete failure, 3 for invalid arguments, 4 for missing dependencies.

#### Scenario: Successful execution
- **WHEN** the full pipeline completes successfully
- **THEN** the system SHALL exit with code 0

#### Scenario: Missing binary dependency
- **WHEN** no splitting backend is available for the input format
- **THEN** the system SHALL exit with code 4 and print a message listing required binaries

### Requirement: Logging
The system SHALL support verbose logging via --verbose / -v flag (DEBUG level) and quiet mode via --quiet / -q flag (WARNING level). Default log level SHALL be INFO.

#### Scenario: Verbose logging
- **WHEN** running with -v flag
- **THEN** the system SHALL print DEBUG-level messages including: each search source queried, each boundary detected, each match confidence score, each external command invoked

#### Scenario: Quiet mode
- **WHEN** running with -q flag
- **THEN** the system SHALL only print WARNING and ERROR messages
