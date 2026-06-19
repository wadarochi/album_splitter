## Why

Users with large collections of single-file CD rips (CDImage FLAC/WAV/APE) have lost their matching CUE sheets and cannot use these files properly in music servers like Ampache. Ampache has explicitly rejected CUE sheet support (GitHub issue #483, closed as `wontfix`), and beets has no native CUE/splitting capability (issue #136, open since 2013). The only viable path is physical splitting, but existing tools require a CUE sheet as input — which is exactly what's missing. There is no end-to-end tool that combines silence-based track boundary detection, multi-source metadata search (including Chinese music databases), CUE generation, lossless splitting, and beets tagging into a single workflow.

## What Changes

- **New CLI tool `cue-finder`** with dual-mode operation: fully non-interactive (flags/args for scripting) and interactive TUI (Textual-based full-screen interface with album search, track list editing, and CUE preview)
- **Silence-based track boundary detection** — reuse the proven RMS algorithm from the existing `audio-slicer` project (`slicer2.py`), outputting timestamp-based boundaries instead of physical audio chunks
- **Multi-source album metadata search** with cascading fallback: MusicBrainz → iTunes → NetEase Cloud Music (pyncm) → Discogs → Deezer → GnuDB. Each source returns track listings with durations. NetEase integration is critical for Chinese/Asian music coverage that Western databases lack
- **DTW-based track matching algorithm** — aligns N silence-detected segments to M database-provided tracks using Dynamic Time Warping with configurable tolerance (default ±3s). Handles segment count mismatch, gapless albums, internal silence false positives, and bonus tracks
- **CUE sheet generation** — produces standard CUE sheets (FILE/TRACK/INDEX 01 MM:SS:FF) from matched boundaries + metadata. CUE serves as an editable intermediate artifact before splitting
- **Lossless audio splitting** with format-specific backends:
  - FLAC: `flac-tracksplit` (frame-level lossless) → `flacsplt` → `shntool` (fallback chain)
  - WAV: Python `wave` module (sample-accurate, zero dependencies)
  - APE: `mac.exe` decode → WAV split → optional re-encode to FLAC (APE cannot be split at frame level)
- **beets integration** — invokes `cuetag` to write CUE metadata to split files, then `beet import` with `chroma` (AcoustID fingerprinting) + `musicbrainz` + `discogs` + `fromfilename` plugins for metadata completion
- **YAML-based tracklist format** — human-readable, commentable project file that stores album info, track list, detected boundaries, match results, and processing state for incremental workflows
- **Skill packaging** — the tool is designed to be invoked as an AI agent skill, with a SKILL.md entry point that enables natural language invocation

## Capabilities

### New Capabilities

- `silence-detection`: RMS-based audio silence analysis that outputs track boundary timestamps from single-file CD rips. Wraps the existing `slicer2.Slicer` algorithm with a timestamp-oriented API (input: audio file path + parameters; output: list of boundary timestamps in seconds). Supports configurable threshold, min length, min interval, hop size, and max silence kept. Streams large files without loading entirely into memory.

- `metadata-search`: Multi-source album/track metadata search with cascading fallback. Searches MusicBrainz, iTunes, NetEase Cloud Music (pyncm), Discogs, Deezer, and GnuDB for album track listings with track durations. Returns normalized results (artist, album title, release date, track titles, track durations in seconds) regardless of source. Supports search by artist+album name, by album ID, or by AcoustID fingerprint. No authentication required for MusicBrainz, iTunes, Deezer, and NetEase (anonymous). Discogs requires a personal access token.

- `track-matching`: DTW-based alignment algorithm that matches N silence-detected audio segments to M database-provided tracks. Uses Dynamic Time Warping with Sakoe-Chiba band constraint (configurable tolerance, default ±3 seconds) as the primary algorithm, with greedy nearest-neighbor matching as fallback. Handles edge cases: segment count ≠ track count, gapless albums (no silence between tracks), internal silence false positives, hidden tracks (HTOA/pregap), and bonus tracks not in original release. Outputs matched track boundaries with confidence scores.

- `cue-generation`: Standard CUE sheet (`.cue` file) generation from matched track boundaries + metadata. Converts sample positions to CUE MSF format (MM:SS:FF, 75 frames/second). Supports PERFORMER, TITLE, FILE, TRACK, INDEX 01 fields. Can also parse existing CUE files for editing/re-generation. CUE serves as the editable intermediate artifact between detection and splitting.

- `audio-splitting`: Lossless audio splitting driven by CUE sheets or timestamp lists. Format-specific backends: FLAC (flac-tracksplit → flacsplt → shntool fallback chain), WAV (Python wave module, sample-accurate), APE (mac.exe decode → WAV split → optional FLAC re-encode). Auto-detects format from file extension. Supports output format conversion (e.g., APE → FLAC). Preserves original audio quality — no lossy re-encoding.

- `beets-tagging`: Integration with beets for metadata tagging of split files. Invokes `cuetag` to write CUE-embedded metadata, then `beet import` with chroma/musicbrainz/discogs/fromfilename plugins for fingerprint-based identification and MusicBrainz matching. Supports both singleton mode (`-s`) for individual tracks and album mode for grouped releases. Configurable beets config path.

- `cli-interface`: Dual-mode CLI tool built with Typer + Rich + Textual. Non-interactive mode: subcommands (search, detect, generate, split, tag, run) with flags/args for scripting and batch processing. Interactive mode: full-screen Textual TUI with album search results table, track list editing, CUE preview, and progress bars. Auto-detects TTY to choose mode. Subcommands can be chained or run individually. Rich-formatted output (tables, progress bars, colored text) in non-interactive mode.

- `tracklist-format`: YAML-based project file format for storing album metadata, track listings, detected boundaries, match results, and processing state. Supports incremental workflows (detect → review → generate → split → tag). Also supports simple plain-text format (one track per line, `Artist - Title` or just `Title`) for quick manual input. Round-trip compatible (can be written, edited by hand, and re-read).

### Modified Capabilities

(No existing capabilities are modified — this is a greenfield project.)

## Impact

- **New project**: `F:\workspace\x20\audio_utils` — independent Python package, not modifying the existing `audio-slicer` project
- **Code reuse**: Imports `slicer2.Slicer` and `slicer2.get_rms` from the existing `audio-slicer` project as a dependency (or vendored copy) for silence detection
- **External dependencies (Python)**: typer, rich, textual, questionary, musicbrainzngs, python3-discogs-client, deezer-python, pyncm, pyacoustid, pyyaml, mutagen, soundfile, numpy
- **External binaries (non-Python, optional)**: flac-tracksplit (Rust, compiled), flacsplt (SourceForge), shntool + flac.exe, mac.exe (Monkey's Audio), ffmpeg, beets — auto-detected at runtime with graceful fallback
- **Target platforms**: Windows (primary, native binaries available for all backends), Linux, macOS
- **Integration points**: 
  - Ampache (consumer of split+tagged files, no modification needed)
  - beets (invoked via subprocess, requires beets installed and configured)
  - audio-slicer project (source of silence detection algorithm)
- **No breaking changes**: This is a new standalone tool, not modifying any existing system
