# cue-finder

End-to-end CLI tool for splitting single-file CD rips (FLAC/WAV/APE) into individual tracks with metadata tagging from MusicBrainz, iTunes, NetEase, Discogs, and Deezer.

## Quick start

```bash
uv sync
uv run cue-finder run -i album.flac --search "Artist Album" -o ./tracks/
```

This runs the full pipeline: detect silence boundaries, search for album metadata, match tracks, generate a CUE sheet, split the audio, and tag the resulting files.

## Installation

### Requirements

- Python 3.10 or newer
- The audio file you want to split (FLAC, WAV, or APE)
- Optional external binaries (see below) for lossless FLAC/APE splitting and beets tagging

### Install from source

This project is managed with [uv](https://docs.astral.sh/uv/). If you don't have uv installed, install it first:

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Then clone and install:

```bash
git clone <repository>
cd cue-finder
uv sync
```

`uv sync` creates a virtual environment (`.venv`) and installs all dependencies from `pyproject.toml`. Run commands through `uv run` so they use the project environment:

```bash
uv run cue-finder run -i album.flac --search "Artist Album" -o ./tracks/
```

To install development dependencies:

```bash
uv sync --extra dev
```

<details>
<summary>Using plain pip instead</summary>

If you prefer not to use uv, the project also works with a standard `pip` workflow:

```bash
git clone <repository>
cd cue-finder
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
pip install -e .
```

Development dependencies:

```bash
pip install -e ".[dev]"
```

</details>

### Platform-specific notes

**Windows**
- The primary development and tested platform.
- Python 3.10–3.12 is supported.
- External binaries (flac-tracksplit, flacsplt, mac.exe, ffmpeg) are easiest to manage by placing them in a single directory and adding that directory to your `PATH`.
- If you use beets, install it in the same Python environment (`pip install beets`).

**Linux**
- Most external tools are available through your distribution's package manager.
- Minimum: `sudo apt install flac shntool ffmpeg` gives FLAC/WAV splitting (`shnsplit`) and CUE-based tagging (`cuetag`).
- Recommended: also `sudo apt install mp3splt` (frame-level splitter, no re-encode) and `uv pip install beets` (advanced tagger).
- `mac` (Monkey's Audio) is not in Debian/Ubuntu main repos — APE inputs require building it from source or using a third-party package.
- `flac-tracksplit` (frame-level lossless FLAC splitter) is also missing from apt; install via `cargo install flac-tracksplit` if you want it.
- See the "Installation examples → Linux (Debian/Ubuntu)" section below for the full apt commands.

**macOS**
- Homebrew is the easiest way to get `flac`, `shntool`, `ffmpeg`, and `beets`.
- `mac` / `mac.exe` for APE decoding is less common on macOS; you may need to build it from source or use a precompiled binary.

## Architecture overview

The project is organized into focused modules:

| Module       | Path                           | Responsibility                                                                                   |
|--------------|--------------------------------|--------------------------------------------------------------------------------------------------|
| `silence`    | `cue_finder/core/silence.py`   | Silence-based track boundary detection using the audio-slicer RMS algorithm.                     |
| `search`     | `cue_finder/core/search.py`    | Multi-source metadata lookup (MusicBrainz, iTunes, NetEase, Discogs, Deezer, GNDB).              |
| `rank`       | `cue_finder/core/rank.py`      | Multi-signal candidate scoring: text similarity, DTW duration alignment, track count, fingerprint. |
| `match`      | `cue_finder/core/match.py`     | Dynamic Time Warping (DTW) and greedy fallback to match detected segments to metadata durations. |
| `interactive`| `cue_finder/core/interactive.py` | Interactive candidate selection with conditional prompting, detail preview, and multi-disc splitting. |
| `cue`        | `cue_finder/core/cue.py`       | CUE sheet generation, parsing, and validation.                                                   |
| `split`      | `cue_finder/core/split.py`     | Audio format detection and orchestration of FLAC/WAV/APE splitting backends.                     |
| `tag`        | `cue_finder/core/tag.py`       | Metadata tagging via cuetag, mutagen fallback, and optional beets import.                        |
| `tracklist`  | `cue_finder/core/tracklist.py` | YAML/text tracklist parsing, validation, and export.                                             |
| `cli`        | `cue_finder/cli.py`            | Typer-based command-line interface with dual TTY/TUI mode.                                       |
| `tui`        | `cue_finder/tui/`              | Textual-based interactive interface (launched automatically in a TTY).                           |
| Backends     | `cue_finder/backends/`         | Format-specific splitting implementations: `flac_splitter`, `wav_splitter`, `ape_splitter`.      |

## External binary dependencies

All external binaries are optional. cue-finder auto-detects available tools at runtime and falls back gracefully when a preferred tool is missing.

| Tool                | Purpose                                          | Windows                                                                                 | Linux                                       | macOS                                         | Fallback if missing                               |
|---------------------|--------------------------------------------------|-----------------------------------------------------------------------------------------|---------------------------------------------|-----------------------------------------------|---------------------------------------------------|
| `flac-tracksplit`   | Native frame-level FLAC splitting                | Download from the Rust crate release page or build with `cargo install flac-tracksplit` | `cargo install flac-tracksplit`             | `cargo install flac-tracksplit`               | `flacsplt`, `shnsplit`, or decode-to-WAV          |
| `flacsplt`          | FLAC splitter from the mp3splt project           | Download from SourceForge mp3splt Windows builds                                        | `apt install mp3splt` / `pacman -S mp3splt` | `brew install mp3splt`                        | `shnsplit` or decode-to-WAV                       |
| `shnsplit` + `flac` | Sample-accurate decode/re-encode for FLAC        | Included with shntool bundles                                                           | `apt install shntool`                       | `brew install shntool`                        | Decode FLAC to WAV and split with the WAV backend |
| `mac.exe` / `mac`   | Decode APE (Monkey's Audio) to WAV               | Download from the Monkey's Audio website                                                | Build from source or use a distro package   | Build from source or use a precompiled binary | APE files cannot be decoded                       |
| `ffmpeg`            | General audio decoding/encoding                  | Download from ffmpeg.org                                                                | `apt install ffmpeg`                        | `brew install ffmpeg`                         | WAV backend for WAV files; soundfile for FLAC     |
| `beet` / `beets`    | Optional advanced tagging and library management | `pip install beets` in the same environment                                             | `pip install beets`                         | `pip install beets`                           | Internal mutagen-based tagging from the CUE sheet |
| `cuetag`            | Apply CUE metadata directly to split files       | Included in shntool bundles                                                             | `apt install shntool`                       | `brew install shntool`                        | mutagen (FLAC/MP3 only)                           |

### Installation examples

**Windows**

```powershell
# Python package
uv sync

# Optional: add precompiled binaries to PATH
$env:Path += ";C:\Tools\cue-finder-bin"
```

**Linux (Debian/Ubuntu)**

Minimum: split FLAC/WAV and tag with the internal mutagen fallback.

```bash
sudo apt install flac shntool ffmpeg
uv sync
```

What each apt package provides:

| apt package     | Binary provided                       | Used by cue-finder for                                           |
|-----------------|---------------------------------------|------------------------------------------------------------------|
| `flac`          | `flac`                                | Encode/decode FLAC; encoder for `shnsplit`.                       |
| `shntool`       | `shnsplit`, `cuetag`                  | Sample-accurate FLAC splitting (`run`/`split`); CUE-based tagging (`tag`). |
| `ffmpeg`        | `ffmpeg`                              | WAV/APE transcoding, general decode/encode fallback.             |

Recommended additions (frame-level splitting with no re-encoding, plus beets tagging):

```bash
# flacsplt — frame-level CUE-based FLAC splitter (preferred over shnsplit)
sudo apt install mp3splt

# beets — advanced tagger used by `run --beets` (default enabled)
# Install it inside the project's venv so it sees the same Python:
uv pip install beets
# Or use the older system beets (may be missing features):
# sudo apt install beets
```

Optional extras:

```bash
# flac-tracksplit — frame-level lossless FLAC splitter (best quality, no re-encode).
# Not packaged by apt; install via cargo or download a prebuilt binary.
cargo install flac-tracksplit

# APE source files (`.ape`) require the `mac` (Monkey's Audio) decoder.
# Not in Debian/Ubuntu main repos — build from source or use a third-party package.
# Without `mac`, APE inputs cannot be decoded; convert to FLAC/WAV first.
```

After installing, verify which backends the tool detects:

```bash
uv run python -c "from cue_finder.core.split import Splitter; print(Splitter().report_backends())"
```

**macOS**

```bash
brew install flac shntool ffmpeg mp3splt
uv sync
uv pip install beets
```

## YAML tracklist format

A tracklist is an editable source of metadata used by the `generate` and `run` commands. The format supports both minimal and complete forms.

### Minimal tracklist

```yaml
album:
  artist: 周杰伦
  title: 范特西
tracks:
  - title: 爱在西元前
  - title: 爸我回来了
  - title: 简单爱
  - title: 忍者
  - title: 开不了口
  - title: 上海一九四三
  - title: 对不起
  - title: 威廉古堡
  - title: 双截棍
  - title: 安静
```

### Complete tracklist

```yaml
album:
  artist: 周杰伦
  title: 范特西
  date: "2001-09-20"
  source: netease
  source_id: "3111188"
tracks:
  - title: 爱在西元前
    artist: 周杰伦
    duration: 236.0
  - title: 爸我回来了
    artist: 周杰伦
    duration: 230.0
  - title: 简单爱
    artist: 周杰伦
    duration: 274.0
  - title: 忍者
    artist: 周杰伦
    duration: 162.0
  - title: 开不了口
    artist: 周杰伦
    duration: 297.0
  - title: 上海一九四三
    artist: 周杰伦
    duration: 201.0
  - title: 对不起
    artist: 周杰伦
    duration: 249.0
  - title: 威廉古堡
    artist: 周杰伦
    duration: 236.0
  - title: 双截棍
    artist: 周杰伦
    duration: 196.0
  - title: 安静
    artist: 周杰伦
    duration: 329.0
detected_boundaries:
  - 236.0
  - 466.0
  - 740.0
  - 902.0
  - 1199.0
  - 1400.0
  - 1649.0
  - 1885.0
  - 2081.0
cue_file: album.cue
output_dir: ./tracks/
```

When used with `run` or `generate`, the durations and boundary information improve matching accuracy. If they are omitted, cue-finder uses the detected silence boundaries and splits the total duration evenly across the track titles.

## CLI subcommands

| Command    | Description                                                                | Key options                                                                                                                                                                                |
|------------|----------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `search`   | Search album metadata across online sources.                               | `query`, `--source`, `--json`                                                                                                                                                              |
| `detect`   | Detect track boundaries via silence detection.                             | `-i`, `--threshold`, `--min-length`, `--min-interval`, `--hop-size`, `--max-sil-kept`, `-o`                                                                                                |
| `generate` | Generate a CUE sheet from detected boundaries and metadata or a tracklist. | `-i`, `--tracklist`, `--search`, `--release-id`, `-o`                                                                                                                                      |
| `split`    | Split an audio file into individual tracks.                                | `-i`, `-c`, `--timestamps`, `-o`, `--format`, `--name-template`                                                                                                                            |
| `tag`      | Tag split audio files with metadata from a CUE sheet.                      | `-d`, `-c`, `--beets/--no-beets`, `--beets-config`, `--beets-mode`                                                                                                                         |
| `run`      | Full pipeline: detect → search → match → generate CUE → split → tag.       | `-i`, `--search`, `--tracklist`, `--release-id`, `-o`, `--format`, `--threshold`, `--min-length`, `--min-interval`, `--hop-size`, `--max-sil-kept`, `--beets/--no-beets`, `--beets-config`, `--beets-mode` |
| `tui`      | Launch the interactive Textual TUI.                                        | none                                                                                                                                                                                       |

### Global options

- `--verbose`, `-v`: Enable debug logging.
- `--quiet`, `-q`: Suppress non-error output.
- `--interactive/--no-interactive`: Force interactive or non-interactive mode.

### `run` options in detail

```bash
cue-finder run -i album.flac --search "Artist Album" -o ./tracks/ --format flac
```

- `-i`, `--input`: path to the source audio file (FLAC/WAV/APE).
- `--search`: free-text album query; the first returned match is used.
- `--tracklist`: path to a YAML tracklist file; overrides `--search` if both are provided.
- `--release-id`: directly fetch an album by `source:id` (e.g. `netease:12345`, `musicbrainz:mbid`); bypasses search and scoring. Use `cue-finder search` to find the correct ID first.
- `-o`, `--output`: directory for the split tracks and generated CUE sheet.
- `--format`: output audio format (`flac` or `wav`). Defaults to the input format.
- `--threshold`: silence threshold in dB (default `-40.0`).
- `--min-length`: minimum track length in milliseconds (default `5000`).
- `--min-interval`: minimum silence interval in milliseconds (default `300`).
- `--hop-size`: hop size in milliseconds (default `10`).
- `--max-sil-kept`: maximum silence kept in milliseconds (default `500`).
- `--beets/--no-beets`: enable or disable the beets import step (default enabled).
- `--beets-config`: path to a custom beets configuration file.
- `--beets-mode`: beets import mode, `album` or `singleton` (default `album`).

### `split` examples

```bash
# Split with a CUE sheet
cue-finder split -i album.flac -c album.cue -o ./tracks/

# Split with explicit timestamps
cue-finder split -i album.wav --timestamps "210.0,435.0,672.0" -o ./tracks/

# Split and convert to FLAC output
cue-finder split -i album.wav -c album.cue -o ./tracks/ --format flac

# Custom filename template
cue-finder split -i album.flac -c album.cue -o ./tracks/ --name-template "{track:02d}. {title}"
```

## TUI usage

When you run `cue-finder` with no subcommand inside a terminal, the tool automatically launches a Textual TUI. You can also launch it explicitly:

```bash
cue-finder tui
```

The TUI guides you through selecting the input file, searching for metadata, reviewing detected boundaries, and running the split/tag pipeline. It is the recommended mode for interactive desktop use. In non-TTY environments (for example, CI pipelines or remote shells without a terminal), the TUI is not launched automatically and you must use the CLI subcommands directly.

To force non-interactive mode in scripts:

```bash
cue-finder --no-interactive run -i album.flac --search "Artist Album" -o ./tracks/
```

## Interactive candidate selection

When the metadata search returns ambiguous results (low confidence score, close competitors, or track count mismatch), cue-finder automatically prompts you to choose from a ranked candidate list instead of blindly auto-selecting the top result.

### When does the prompt appear?

The interactive prompt triggers when any of these conditions are met:

- Top candidate score is below 0.50 (low confidence).
- The top two candidates are within 0.10 of each other (strong competition).
- The top candidate has warning flags (track count or duration mismatch).

You can override this behavior with global flags:

- `--interactive`: always prompt, even for high-confidence matches.
- `--no-interactive`: never prompt, always auto-select the top candidate.

### The selection interface

```
┌─────────────────────────────────────────────────────┐
│  Candidates for "S.H.E Play"  (10 tracks, 40:00)    │
├────┬──────────┬──────────┬──────┬──────┬──────┬─────┤
│ #  │ Artist   │ Album    │ Year │ Trk  │ Src  │ Score│
├────┼──────────┼──────────┼──────┼──────┼──────┼─────┤
│ 1  │ S.H.E    │ Play     │ 2007 │   11 │itunes│ 0.42│
│ 2  │ S.H.E    │ Play(豪华)│ 2007 │   12 │netease│0.39│
└────┴──────────┴──────────┴──────┴──────┴──────┴─────┘

Select [1-2], (d)etail, (s)kip, (m)anual, (q)uit (1):
```

- **Number**: select that candidate.
- **d**: view track-by-track alignment detail (expected vs actual duration, confidence).
- **s**: skip selection, use numbered tracks.
- **m**: enter a new search query and re-search.
- **q**: abort.

### Direct fetch with `--release-id`

When search consistently returns wrong results (e.g. short or generic album titles), you can bypass search entirely by specifying a known source ID:

```bash
# First, find the correct ID
cue-finder search "S.H.E Play" --json

# Then fetch directly
cue-finder run -i album.flac --release-id itunes:456173869 -o ./tracks/
```

This skips the search and scoring pipeline entirely, fetching the exact album from the specified source.

### Multi-disc album splitting

When you select a candidate whose track count significantly exceeds the number of detected segments (e.g. a combined CD1+CD2 release with 17 tracks, but only 10 segments detected), cue-finder offers a disc-range selection:

```
⚠ Track count mismatch: Album has 17 tracks, but 10 segments detected.
This may be a multi-disc album. Select a track subset.

  1. Disc 1: tracks 1-10 (10 tracks) <- matches detected
  2. Disc 2: tracks 11-17 (7 tracks)
  3. First half: tracks 1-8 (8 tracks)
  4. Second half: tracks 9-17 (9 tracks)
  a. All 17 tracks

Select [1-N], enter range (e.g. 3-12), or 'a' (1):
```

You can pick a suggestion by number, type a custom range (e.g. `11-17`), or select `a` to keep all tracks. The selected subset is then used for track matching and CUE generation.

In the TUI, this appears as a modal dialog with a full track listing and a range input field.

## Metadata sources

Default search cascade (first source with usable results wins):

1. MusicBrainz
2. iTunes
3. NetEase
4. Discogs
5. Deezer
6. GNDB

For Chinese, Japanese, Korean, and other Asian releases, NetEase is usually the best source. Pass `--source netease` to `search` or use a NetEase-sourced tracklist.

Some sources require credentials or configuration:

- **Discogs**: requires a `DISCOGS_TOKEN` environment variable. Generate a personal access token at discogs.com/settings/developers.
- **AcoustID fingerprinting**: requires an `ACOUSTID_API_KEY` environment variable. This is currently used only by the library API for ambiguous identification, not by the default CLI pipeline.

## Common workflows

### Full automatic pipeline

```bash
cue-finder run -i album.flac --search "Artist Album" -o ./tracks/
```

### Search first, then decide

```bash
cue-finder search "Artist Album" --json
cue-finder run -i album.flac --search "Artist Album" -o ./tracks/
```

### Direct fetch by release ID

When search returns wrong results for short or generic album titles:

```bash
cue-finder search "Artist Album" --json          # find the correct source:id
cue-finder run -i album.flac --release-id itunes:456173869 -o ./tracks/
```

### Multi-disc album workflow

When the album is a combined CD1+CD2 release but you only have one disc's audio file:

```bash
# Search finds the combined version (17 tracks)
cue-finder run -i forever_cd1.flac --search "S.H.E Forever" -o ./tracks/
# Interactive prompt offers disc-range selection -> pick "Disc 1: tracks 1-10"
```

### Manual tracklist workflow

```bash
# Create tracklist.yaml by hand or from search results
cue-finder generate -i album.flac --tracklist tracklist.yaml -o album.cue
cue-finder split -i album.flac -c album.cue -o ./tracks/
cue-finder tag -d ./tracks/ -c album.cue
```

### Incremental workflow with YAML tracklist

```bash
# 1. Search and save a starting tracklist (you can edit it later)
cue-finder search "Artist Album" --json > results.json
# 2. Convert the chosen result to tracklist.yaml (manually or with a helper script)
# 3. Run the pipeline using the tracklist
cue-finder run -i album.flac --tracklist tracklist.yaml -o ./tracks/
```

## Testing

```bash
uv run pytest
```

Integration and slow tests can be skipped with:

```bash
uv run pytest -m "not integration and not slow"
```

## License

MIT
