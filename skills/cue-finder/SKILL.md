# cue-finder

End-to-end CLI tool for splitting single-file CD rips (FLAC/WAV/APE) into individual tracks with metadata tagging from MusicBrainz, iTunes, NetEase, Discogs, and Deezer.

## Invocation

- Trigger: `split this CD rip`, `find track boundaries`, `generate CUE sheet`, `tag split files`, `用 cue-finder 拆分这个CDImage`, `split this album into tracks`, `create individual tracks from CDImage`
- Binary: `cue-finder` (entry point: `cue_finder.cli:app`)
- Default: dual-mode. When invoked with no subcommand in a terminal (TTY), it launches the Textual TUI. In non-TTY environments (CI, pipelines, headless servers) it runs in non-interactive CLI mode. You can force a mode with `--interactive` or `--no-interactive`.
- Prefer NetEase (pyncm) for Chinese/Asian music searches because the metadata is usually more accurate and complete for those releases.

## Natural language → subcommand mapping

| User phrase | Subcommand | Purpose |
|-------------|------------|---------|
| "find this album", "search metadata for...", "look up album" | `search` | Query MusicBrainz, iTunes, NetEase, Discogs, Deezer, GNDB for album metadata. |
| "detect track boundaries", "find silence points", "find split points" | `detect` | Run silence-based boundary detection on the input audio. |
| "generate CUE sheet", "create CUE from tracklist" | `generate` | Build a CUE sheet from detected boundaries + metadata or a YAML tracklist. |
| "split this CDImage", "split the audio into tracks" | `split` | Split the source file into individual tracks using a CUE or timestamps. |
| "tag the split files", "write metadata to tracks" | `tag` | Apply tags from a CUE sheet, with optional beets import. |
| "split this album into tracks", "create individual tracks from CDImage", "run the full pipeline" | `run` | Full pipeline: detect → search → match → generate CUE → split → tag. |
| "open the UI", "interactive mode", "launch TUI" | `tui` | Launch the Textual TUI. |

## Non-interactive CLI usage for AI agents

Always prefer explicit non-interactive subcommands when automating. Provide `-i`/`--input` and `-o`/`--output` for every operation that touches files. Use `-q` for quiet output and `-v` for debug logs.

### Full pipeline (most common)

```bash
cue-finder run -i album.flac --search "Artist Album" -o ./tracks/
```

### Full pipeline with Chinese/Asian music (force NetEase)

```bash
cue-finder run -i album.flac --search "周杰伦 范特西" -o ./tracks/
```

`run` will query sources in the default priority order and will use NetEase if it returns the best match. To restrict the search to a single source, use the `search` subcommand first and then pass a tracklist.

### Search only

```bash
cue-finder search "Pink Floyd The Dark Side of the Moon" --json
cue-finder search "王菲 唱游" --source netease --json
```

### Detect boundaries only

```bash
cue-finder detect -i album.flac -o boundaries.json
```

### Generate CUE from search

```bash
cue-finder generate -i album.flac --search "Artist Album" -o album.cue
```

### Generate CUE from a YAML tracklist

```bash
cue-finder generate -i album.flac --tracklist tracklist.yaml -o album.cue
```

### Split only

```bash
cue-finder split -i album.flac -c album.cue -o ./tracks/
```

### Split by raw timestamps

```bash
cue-finder split -i album.flac --timestamps "210.0,435.0,672.0" -o ./tracks/
```

### Tag only

```bash
cue-finder tag -d ./tracks/ -c album.cue --beets
```

### Incremental workflow (search → tracklist → split → tag)

1. Search for metadata and export the chosen release to a YAML tracklist.
2. Review or edit `tracklist.yaml`.
3. Generate CUE and run the rest of the pipeline with the tracklist.

```bash
# 1. Search (inspect JSON, pick the correct release)
cue-finder search "Artist Album" --json > results.json

# 2. Create a tracklist.yaml from the results (or by hand), then:
cue-finder generate -i album.flac --tracklist tracklist.yaml -o album.cue
cue-finder split -i album.flac -c album.cue -o ./tracks/
cue-finder tag -d ./tracks/ -c album.cue

# Or combine generate/split/tag back into a single run command:
cue-finder run -i album.flac --tracklist tracklist.yaml -o ./tracks/
```

## YAML tracklist format

A minimal tracklist contains only `album` and `tracks`. A complete tracklist can include `detected_boundaries`, `cue_file`, `output_dir`, and multi-disc `discs`.

```yaml
album:
  artist: 周杰伦
  title: 范特西
  date: "2001-09-20"
  source: netease
  source_id: "3111188"
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

For per-track artists or durations, add `artist` and `duration` to each track entry.

```yaml
album:
  artist: Various Artists
  title: Compilation
tracks:
  - title: Song A
    artist: Artist One
    duration: 210.0
  - title: Song B
    artist: Artist Two
    duration: 225.0
```

## Dual-mode operation rules

- `cue-finder` with no subcommand in a TTY → launches `cue-finder tui`.
- `cue-finder` with no subcommand in a non-TTY environment → stays in CLI mode and prints help.
- In automation, always pass the exact subcommand (e.g., `run`) so you are not surprised by TUI mode.
- Force non-interactive mode when running in CI/headless: `cue-finder --no-interactive run ...`.

## Metadata search priority

Default cascade order when no `--source` is given:

1. `musicbrainz`
2. `itunes`
3. `netease`
4. `discogs`
5. `deezer`
6. `gnudb`

When a source returns usable results, the remaining sources are skipped. To override, use `cue-finder search --source <source>` or provide a tracklist. For Chinese/Asian music, NetEase is preferred because it generally has better local coverage; use `--source netease` or a tracklist with `source: netease`.

## Output conventions

- Generated CUE files are written with UTF-8 BOM for compatibility with Windows tools.
- Split filenames default to `{track:02d} - {title}.{format}`.
- The `run` command creates output in the directory specified by `-o` and places the CUE sheet next to the tracks as `<input_stem>.cue`.

## Error handling for agents

- `EXIT_INVALID_ARGS` (3): missing/invalid arguments, missing input file, bad timestamps.
- `EXIT_MISSING_DEPS` (4): missing external binary dependency (e.g., TUI module not available, APE decoder not found).
- `EXIT_PARTIAL` (1): metadata search returned no results but the pipeline still produced numbered tracks.
- `EXIT_FAILURE` (2): unexpected runtime failure during detect/search/split/tag.

When a command returns a non-zero exit code, check the last console output line or run again with `-v` for full debug logs.
