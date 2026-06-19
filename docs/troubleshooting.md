# Troubleshooting

## Missing binary errors

cue-finder depends on external command-line tools for certain audio formats. All external binaries are optional — cue-finder auto-detects them at runtime.

### "flac-tracksplit not found" or "flacsplt not found"

FLAC splitting requires one of these tools. If none are available, cue-finder falls back to decoding FLAC to WAV and splitting with the WAV backend.

| Platform | Installation |
|----------|-------------|
| **Windows** | Download precompiled binaries: [flac-tracksplit](https://github.com/martinm-rs/flac-tracksplit/releases) or [flacsplt](https://sourceforge.net/projects/mp3splt/) |
| **Linux** | `apt install mp3splt` (includes flacsplt) or `apt install shntool flac` |
| **macOS** | `brew install mp3splt` or `brew install shntool flac` |

Verify installation:

```bash
flac-tracksplit --version
# or
flacsplt --version
# or
shnsplit --version
```

### "mac.exe not found" (APE splitting)

Monkey's Audio (APE) files require `mac.exe` for decoding.

| Platform | Installation |
|----------|-------------|
| **Windows** | Download from the [Monkey's Audio website](https://www.monkeysaudio.com/) |
| **Linux** | `apt install monkeys-audio` (may need to build from source on some distros) |
| **macOS** | Build from source: `brew install monkeysaudio` or compile from [official source](https://www.monkeysaudio.com/) |

Without `mac`, APE files cannot be split.

### "ffmpeg not found"

ffmpeg is an optional general-purpose fallback. It is not required if format-specific tools (flac-tracksplit/flacsplt/shnsplit for FLAC, wave module for WAV) are available.

Verify:

```bash
ffmpeg -version
```

### "shnsplit not found" or "shntool not found"

`shnsplit` is part of the `shntool` package and provides a reliable fallback for FLAC splitting when paired with `flac`.

| Platform | Installation |
|----------|-------------|
| **Windows** | Download shntool binaries from the Windows shntool bundle |
| **Linux** | `apt install shntool flac` |
| **macOS** | `brew install shntool flac` |

## API rate limits

### MusicBrainz

MusicBrainz enforces a rate limit of approximately 1 request per second per IP address. If you exceed this limit, you will receive HTTP 503 responses. cue-finder implements exponential backoff (up to 3 retries).

**Solutions:**
- Wait and retry.
- Reduce the number of search queries.
- If you use MusicBrainz heavily, consider running a local MirrorBrainz instance.

### Discogs

Discogs requires a personal access token set as the `DISCOGS_TOKEN` environment variable. Without this token, the Discogs adapter is skipped.

```bash
# Linux/macOS
export DISCOGS_TOKEN="your_token_here"

# Windows (PowerShell)
$env:DISCOGS_TOKEN = "your_token_here"

# Windows (cmd)
set DISCOGS_TOKEN=your_token_here
```

Generate a token at: [discogs.com/settings/developers](https://www.discogs.com/settings/developers)

Rate limit: 60 requests per minute for authenticated users, 25 for unauthenticated.

### NetEase Cloud Music (pyncm)

NetEase's API does not require authentication but may occasionally be inaccessible outside of China. If the NetEase adapter fails, cue-finder falls back to the next source in the cascade.

### AcoustID

AcoustID fingerprinting requires an API key set as the `ACOUSTID_API_KEY` environment variable. This is currently only used by the internal library API, not by the default CLI pipeline.

```bash
export ACOUSTID_API_KEY="your_key_here"
```

## Match failures

### Low confidence scores

The track matcher uses Dynamic Time Warping (DTW) to align detected boundaries with expected track durations. Low confidence scores indicate a mismatch between audio duration and metadata durations.

**Common causes:**

1. **Different masterings**: The CD rip may be a different pressing/mastering than the metadata source. Track order may differ, or bonus tracks may be present.

2. **Missing or extra tracks**: If the metadata has more tracks than detected segments (or vice versa), confidence decreases. Check if the audio has HTOA (Hidden Track One Audio) before index 01, or bonus tracks.

3. **Gapless albums**: Albums with no silence between tracks (classical, live, DJ mixes) cannot be split by silence detection alone.

**Solutions:**
- Use the `--threshold` flag to adjust silence sensitivity (default: -40 dB). Try -30 dB for gapless or quiet albums.
- Use `--min-length` and `--min-interval` to tune detection parameters.
- Manually create a tracklist YAML with correct durations and use `cue-finder generate --tracklist`.
- For gapless albums, split by equal spacing from a verified tracklist.

### "No boundaries detected"

This means the silence detection algorithm found no clear silence regions. Possible causes:

- The album is a gapless recording (no silence between tracks).
- The silence threshold is too strict. Try a higher value (e.g., `--threshold -30`).
- The audio has continuous noise or very quiet sections that are treated as signal.

## Audio format issues

### Unsupported file format

cue-finder supports FLAC, WAV, and APE input files. Other formats (MP3, AAC, OGG) are not supported as input because lossy-to-lossy splitting degrades quality.

If you have a different format, convert to FLAC or WAV first using ffmpeg:

```bash
ffmpeg -i input.m4a -c flac output.flac
```

### Corrupt audio file

If detection or splitting fails with unexpected errors, the audio file may be corrupted.

**Solutions:**
- Verify the file plays correctly in a standard audio player.
- Use `ffmpeg` to re-encode the file: `ffmpeg -i corrupted.flac -c flac repaired.flac`
- Check that the sample rate and channel count are standard values.

### Soundfile errors

soundfile (libsndfile) is used for reading and writing some audio formats. If you encounter errors like "Format not recognised", the audio file may use an unsupported codec or have an unusual header.

## beets integration issues

### "beet not found"

beets is an optional dependency for advanced metadata tagging. If `beet` is not in your PATH, cue-finder falls back to mutagen-based tagging from the CUE sheet.

Install beets:

```bash
pip install beets
```

### Missing recommended plugins

beets uses plugins for enhanced metadata lookup. cue-finder checks for these recommended plugins in the beets config:

- `chroma` — AcoustID fingerprinting for accurate identification
- `fromfilename` — Parse track numbers and titles from filenames
- `discogs` — Discogs metadata lookup
- `musicbrainz` — MusicBrainz metadata lookup

**Solutions:**
1. Add the plugins to your beets config (`~/.config/beets/config.yaml`):
   ```yaml
   plugins:
     - chroma
     - fromfilename
     - discogs
     - musicbrainz
   ```
2. Or use `--no-beets` to skip beets and rely on CUE metadata only.

### beets config not found

cue-finder looks for beets configuration at platform default locations:
- **Windows**: `%APPDATA%\beets\config.yaml`
- **Linux**: `~/.config/beets/config.yaml`
- **macOS**: `~/Library/Application Support/beets/config.yaml`

Use `--beets-config` to specify a custom path:

```bash
cue-finder tag -d ./tracks/ -c album.cue --beets-config /custom/path/config.yaml
```

### Singleton vs album mode

- **album mode** (`--beets-mode album`): Treats all tracks as a single release. Best for album splitting.
- **singleton mode** (`--beets-mode singleton`): Tags each track individually. Best for compilations or bonus tracks.

Default is album mode. Switch to singleton if beets can't match as an album:

```bash
cue-finder tag -d ./tracks/ -c album.cue --beets-mode singleton
```
