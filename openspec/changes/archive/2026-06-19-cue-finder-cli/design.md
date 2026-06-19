## Context

Users have large collections of single-file CD rips (CDImage FLAC/WAV/APE) with lost CUE sheets. They need to split these into individual track files for use in Ampache (which rejected CUE support in issue #483) and tag them with correct metadata via beets (which has no native CUE/splitting support, issue #136 open since 2013).

The existing `audio-slicer` project (F:\workspace\x20\audio-slicer) provides a proven RMS-based silence detection algorithm (`slicer2.py`) with streaming I/O and 400x real-time performance. This project reuses that algorithm but wraps it in a complete end-to-end workflow: detect → search → match → generate CUE → split → tag.

The tool must work on Windows (primary platform) with native binaries for all audio backends. It must support Chinese/Asian music via NetEase Cloud Music API, which Western databases (MusicBrainz, Discogs) poorly cover.

## Goals / Non-Goals

**Goals:**
- End-to-end CLI tool that takes a single-file CD rip and produces individually tagged track files
- Dual-mode: non-interactive (scriptable with flags) and interactive (Textual TUI)
- Lossless splitting for FLAC (frame-level), WAV (sample-accurate), and APE (decode-then-split)
- Multi-source metadata search with Chinese music support (NetEase)
- DTW-based track matching that handles imperfect silence detection
- CUE sheet as editable intermediate artifact
- beets integration for metadata tagging
- Skill-packagable for AI agent invocation

**Non-Goals:**
- GUI application (the existing audio-slicer GUI remains separate)
- Audio playback or preview functionality
- Online CUE sheet database / sharing platform
- Modifying Ampache source code to add CUE support
- Modifying beets source code to add splitting support
- Real-time audio processing (batch processing only)
- Support for video files or non-CD audio formats (e.g., podcast splitting)
- Automatic album identification without any user input (some user confirmation is required for ambiguous matches)

## Decisions

### D1: Reuse `slicer2.py` algorithm rather than reimplementing or using external tools

**Choice**: Import/vendor the `Slicer` class and `get_rms` function from the existing `audio-slicer` project.

**Rationale**: The algorithm is proven (400x real-time, streaming I/O, comprehensive tests), well-understood, and already handles edge cases (leading/trailing silence, multiple silence windows). Reimplementing would risk regressions; using external tools (ffmpeg silencedetect, pydub) would add dependencies without clear benefits.

**Alternatives considered**:
- `ffmpeg silencedetect`: More precise (sample-level) but requires subprocess parsing and loses the streaming RMS optimization
- `pydub silence detection`: Simpler API but O(n) slice operations are slow for long files (~450s for 100min audio)
- `aubio onset detection`: Fast C-based but detects onsets (musical events), not track boundaries

### D2: DTW as primary matching algorithm, greedy as fallback

**Choice**: Dynamic Time Warping with Sakoe-Chiba band constraint (tolerance window) as primary; greedy nearest-neighbor matching as fallback for simple cases.

**Rationale**: DTW handles the core challenge — N detected segments may not equal M expected tracks, and durations may not match exactly. The ConvDTW-ACS paper demonstrates 166ms mean error for DTW-based audio segmentation. Greedy matching is simpler and faster for well-separated albums where N == M and durations match closely.

**Tolerance values** (from MIREX evaluation standards):
- ±0.5s: strict (used for confidence scoring)
- ±3.0s: default (practical for CD track boundaries)
- ±5.0s: relaxed (for poor-quality rips or variable-speed media)

**Alternatives considered**:
- Pure greedy matching: Fails for gapless albums and duration mismatches
- Hidden Markov Models: Overkill for this problem; requires training data
- mp3splt `-a` mode: Searches ±gap seconds around expected splitpoint for lowest RMS — this is actually a local optimization we incorporate as a post-DTW refinement step

### D3: Cascading metadata source fallback (MusicBrainz → iTunes → NetEase → Discogs → Deezer → GnuDB)

**Choice**: Multi-source search with automatic fallback. Results are normalized to a common schema regardless of source.

**Rationale**: No single source covers all music. MusicBrainz is open and detailed but has gaps in Chinese music. iTunes has excellent Asian coverage and requires no authentication. NetEase (pyncm) is critical for Chinese music — its `dt` field provides millisecond-accurate track durations. Discogs is strong for physical releases (vinyl/CD). Deezer requires no auth and is fast. GnuDB is a legacy fallback.

**Authentication requirements**:
- No auth: MusicBrainz (User-Agent only), iTunes, Deezer, NetEase (anonymous), GnuDB
- Token required: Discogs (personal access token)
- API key: AcoustID (for fingerprint-based identification)

**Alternatives considered**:
- Single source (MusicBrainz only): Insufficient Chinese coverage
- Spotify Web API: Requires OAuth 2.0, not available in mainland China, weak Chinese catalog
- Last.fm: Unreliable track durations (must query each track individually)

### D4: Format-specific splitting backends with auto-detection and fallback

**Choice**: 
- FLAC: `flac-tracksplit` (Rust, frame-level lossless) → `flacsplt` → `shntool` + `flac.exe`
- WAV: Python `wave` module (native, sample-accurate, zero dependencies)
- APE: `mac.exe` decode → WAV split → optional re-encode to FLAC

**Rationale**: 
- `ffmpeg -c copy` has a known bug for FLAC (duration metadata not updated, MD5 mismatch) — explicitly avoided
- `soundfile`/`libsndfile` re-encodes FLAC (mathematically lossless but not byte-identical frames)
- APE cannot be split at frame level by any tool — must decode to WAV first
- Python `wave` module is ideal for WAV: native, sample-accurate, no external dependencies
- `flac-tracksplit` is the only true frame-level lossless FLAC splitter, but requires Rust compilation

**Alternatives considered**:
- FFcuesplitter (Python): Uses ffmpeg under the hood, re-encodes FLAC due to the ffmpeg bug
- Medieval CUE Splitter: Windows GUI only, not scriptable
- CUETools: .NET application, CLI doesn't close on completion (can't loop)

### D5: YAML tracklist format with plain-text fallback

**Choice**: YAML as primary project file format (stores album info, track list, detected boundaries, match results, processing state). Plain text (one track per line) for quick manual input.

**Rationale**: YAML is human-readable, supports comments (unlike JSON), supports complex structures (nested album/tracks), and is round-trip compatible. Plain text is for users who just want to type track titles quickly. The tool converts plain text to YAML internally.

**Alternatives considered**:
- JSON: No comments, less human-friendly
- TOML: Good for config but awkward for lists of tracks
- CSV: No nesting, no comments
- CUE sheet as the only format: CUE doesn't support comments or arbitrary metadata; better as an output artifact

### D6: Typer + Rich + Textual for CLI/TUI dual-mode

**Choice**: Typer for CLI argument parsing, Rich for non-interactive output formatting, Textual for interactive full-screen TUI.

**Rationale**: 
- Typer (v0.26.7, June 2026): Type-hint based CLI, vendors Click internally, ships with Rich
- Rich (v15.0.0, April 2026): Best-in-class terminal formatting (tables, progress bars, panels)
- Textual (v8.2.7, May 2026): Best Python TUI framework, first-class Windows support, built on Rich
- All three are actively maintained, have excellent Windows compatibility, and integrate seamlessly

**Dual-mode pattern**: Auto-detect TTY (`sys.stdin.isatty()`). Terminal → TUI; pipe/script → non-interactive. User can force mode with `--interactive`/`--no-interactive` flag.

**Alternatives considered**:
- Cyclopts: More advanced type support but 20x smaller community than Typer
- urwid: Poor Windows support (needs windows-curses)
- prompt_toolkit: Too low-level for full-screen TUI
- Trogon: Auto-generates form-based TUI from CLI, but we need custom TUI (search results, track editing)

### D7: CUE sheet as editable intermediate artifact (not just output)

**Choice**: The workflow always produces a CUE sheet before splitting. Users can edit the CUE (adjust boundaries, fix titles) before the split step. The CUE is the contract between detection and splitting.

**Rationale**: Silence detection is imperfect. Having an editable CUE between detection and splitting allows human review without re-running detection. The CUE is also a standard archival format that can be stored alongside the audio file.

### D8: beets integration via subprocess (not embedded)

**Choice**: Invoke `beet import` and `cuetag` via subprocess rather than importing beets as a Python library.

**Rationale**: beets' internal API (`beets.autotag`, `beets.library`) requires a configured beets database and config file — too heavy a dependency for a standalone tool. Subprocess invocation keeps the tools decoupled and allows users to use their existing beets configuration.

## Risks / Trade-offs

- **[pyncm is archived (2026-03)]** → Mitigation: Pin version in dependencies. If API breaks, fall back to `api-enhanced` (Node.js) running as local HTTP service, or `Class163-NexT` (async Python, actively maintained). The NetEase API protocol is stable; only the wrapper library is archived.

- **[flac-tracksplit requires Rust compilation]** → Mitigation: Auto-detect at runtime. Fallback chain: flac-tracksplit → flacsplt (pre-built Windows binary) → shntool (pre-built). Document compilation instructions in README. Consider providing pre-built binaries in releases.

- **[APE splitting requires full decode (no frame-level splitting)]** → Mitigation: Document this limitation clearly. Default APE workflow converts to FLAC (more widely supported, better metadata). Keep original APE file intact as backup.

- **[DTW matching may produce incorrect results for gapless albums]** → Mitigation: Use onset detection (librosa) as secondary signal for gapless transitions. Always present match results with confidence scores in TUI for human review. Allow manual boundary adjustment before CUE generation.

- **[Multiple external binary dependencies (flac-tracksplit, flacsplt, shntool, mac.exe, ffmpeg, beets)]** → Mitigation: Auto-detect available binaries at startup with clear status reporting. Graceful degradation — each format has a fallback chain. Document installation for each platform. Consider bundling some binaries in releases.

- **[NetEase API legal gray area]** → Mitigation: Use only for metadata search (not downloading). Document as "for personal use with legally owned CDs." No API key distribution — users provide their own if needed.

- **[Discogs requires personal access token]** → Mitigation: Make Discogs optional (skip if no token configured). MusicBrainz + iTunes + NetEase cover most use cases without authentication.

- **[Track count mismatch (N ≠ M) is common]** → Mitigation: DTW handles this algorithmically. TUI shows unmatched segments/tracks with low confidence. User can manually merge, split, or skip segments before CUE generation.

- **[Large file memory usage]** → Mitigation: Reuse the streaming I/O pattern from `gui/slicing_tasks.py` (`build_rms_list_from_file` with 131072-frame read blocks, `write_slice_range` with 65536-frame chunk writes). Never load entire file into memory.

## Open Questions

- Should the tool support embedded CUE sheets (FLAC CUESHEET metadata block) as input, or only external `.cue` files? (Current design: external only; embedded support can be added later via mutagen)
- Should the tool integrate with AccurateRip/CTDB for verification of split tracks? (Current design: no — this requires the original CD or a reference database; out of scope for CUE-less rips)
- Should the tool support batch processing of multiple albums in a directory? (Current design: yes, via `cue-finder run --batch ./collection/` — but this requires per-album metadata search, which may need user interaction for ambiguous matches)
- Should the YAML tracklist format support multiple disc albums (e.g., 2CD sets)? (Current design: yes — `discs:` array in YAML, each disc is a separate FILE entry in CUE)
