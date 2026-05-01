# NVR

Multi-camera IP CCTV recorder with a **browser dashboard** for live viewing and a **recordings browser**. Recordings use [FFmpeg](https://ffmpeg.org/)'s segment muxer (MPEG-TS or MP4 on disk). Live view runs **one FFmpeg process per camera** to publish **HLS** (`stream.m3u8` + MPEG-TS segments). Browsers play that stream with [hls.js](https://github.com/video-dev/hls.js/) (or Safari's native HLS).

## Features

- **Multiple streams** — separate supervisor loop per camera; one camera failing does not stop the others.
- **Optional multiscreen stream** — compose multiple cameras into one HLS mosaic (`/live/multiscreen/stream.m3u8`) while keeping per-camera streams unchanged.
- **Disk recording** — time-segmented MPEG-TS/MP4 under a configurable root (`-c copy`, low CPU when the source is already H.264).
- **Web UI** — responsive grid of live tiles with per-camera status dots; [FastAPI](https://fastapi.tiangolo.com/) serves the app, the health API, and static HLS under `/live/…`.
- **Recordings browser** — `/recordings` page lists clips per camera with inline playback and download links (supports HTTP `Range` for scrubbing).
- **Health API** — `/api/health` exposes per-pipeline state (running, restarts, uptime, last error) and HLS playlist freshness for external monitoring.
- **Automatic FFmpeg restart** — exponential backoff capped at 60 seconds; resets after a healthy run; gives up on permanent failures (wrong URL/creds) rather than looping forever.
- **Per-camera stderr logs** — FFmpeg output routed to `nvr.ffmpeg.{record|hls}.{camera_id}` loggers with `user:password@` redaction.
- **Process-group shutdown** — SIGINT / SIGTERM stops FFmpeg children (and any grandchildren) cleanly.
- **Record / live toggles** — enable either or both globally, or per-camera, from the config file or the CLI.

### Process model (default)

With **recording and web both enabled**, each camera runs **two** FFmpeg processes: one for segmented recording and one for HLS. That roughly doubles network and CPU use versus **record-only** or **live-only**. Use `--no-web` or `live: false` for archive-only; use `--no-record` or `record: false` for live-only (recommended for low-CPU setups).

## Requirements

- **Python** 3.10+
- **FFmpeg** on your `PATH`
- **Python packages** in `requirements.txt`: PyYAML, python-dotenv, FastAPI, Uvicorn

## Quick start

See [QUICKSTART.md](QUICKSTART.md).

## Project layout

```text
NVR/                    # run all commands from this directory
  config/
    cameras.example.yaml
    cameras.yaml        # create locally; gitignored by default
  nvr/                  # Python package
    __main__.py         # python -m nvr
    cli.py
    settings.py
    supervisor.py       # FFmpeg process supervision + backoff
    state.py            # in-memory pipeline health registry
    recorder.py         # record FFmpeg command builder
    hls_live.py         # HLS FFmpeg command builder
    recordings.py       # on-disk recordings listing/resolution
    ffmpeg_common.py    # shared FFmpeg command fragments
    web_app.py          # FastAPI app
    static/
      index.html        # live dashboard
      recordings.html   # recordings browser
      css/main.css
      js/app.js
      js/recordings.js
  recordings/           # MPEG-TS/MP4 archive; contents gitignored; .gitkeep kept
  data/                 # HLS cache for live view (gitignored)
  requirements.txt
  README.md
  QUICKSTART.md
  .env                  # credentials; gitignored
  .env.example
  .gitignore
```

Run from the **repository root** (the directory that contains the `nvr` package):

```bash
python3 -m nvr
```

## Configuration

Copy `config/cameras.example.yaml` to `config/cameras.yaml`.

**Relative paths** in the YAML (`recordings_dir`, `hls_dir`) are resolved against the **directory that contains the config file** (i.e. `config/`). Example: `../recordings` → `NVR/recordings/`, `../data/hls` → `NVR/data/hls/`.

### Top-level keys

| Key | Description |
|-----|-------------|
| `recordings_dir` | Root directory for segmented recordings. |
| `hls_dir` | Root for HLS playlists and `.ts` files (exposed as `/live/<camera_id>/…`). |
| `recording_format` | `mpegts` (default) writes `.ts` segments; `mp4` writes `.mp4`. MPEG-TS is more reliable for **codec copy** with H.264/H.265 from RTSP. |
| `segment_seconds` | Recording segment length in seconds (minimum **30** enforced). |
| `rtsp_transport` | FFmpeg `-rtsp_transport` (`tcp` by default). Also accepts `udp`, `udp_multicast`, `http`. |
| `record` | Global enable for disk recording (`true` by default). Per-camera overrides below. |
| `live` | Global enable for HLS/web (`true` by default). Per-camera overrides below. |
| `live_hls` | Live HLS tuning knobs (`segment_seconds`, `list_size`, `delete_threshold`, `playlist_fresh_seconds`, `target_latency_seconds`). |
| `multiscreen` | Optional single mosaic HLS output built from selected live cameras (disabled by default). |
| `web.host` / `web.port` | HTTP bind address and port (`0.0.0.0` and **8765** by default). |
| `cameras` | List of cameras — see below. |

### Per-camera keys

| Key | Description |
|-----|-------------|
| `url` | **Required.** RTSP/HTTP(S) source. Supports `${ENV_VAR}` interpolation. |
| `id` | **Required** in practice (defaults to `cam{N}`); used as a directory name, must match `^[A-Za-z0-9][A-Za-z0-9_-]*$`, unique across the config. |
| `name` | Display name for the UI. Defaults to `id`. |
| `hevc_tag` | `true` adds `-tag:v hvc1` for H.265 in MP4/HLS. Omit for H.264-only. |
| `record` | Override the global `record` toggle for this camera. |
| `live` | Override the global `live` toggle for this camera. |
| `enabled` | `false` disables both record and live for this camera. Default `true`. |

### Optional multiscreen keys

The `multiscreen` block is disabled by default. When enabled, NVR starts a separate FFmpeg compositor that decodes selected live cameras, arranges them into a grid, and publishes a single HLS stream.

| Key | Description |
|-----|-------------|
| `enabled` | Enable multiscreen compositor (`false` by default). |
| `camera_ids` | Optional list of camera IDs to include; if omitted/empty, all live-enabled cameras are used. |
| `cols` | Number of grid columns. Rows are auto-calculated. |
| `tile_width` / `tile_height` | Pixel size for each tile before stacking (default `640x360`). |
| `fps` | Output frame rate for the combined stream (default `10`). |
| `bitrate` | Encoder bitrate for the combined stream (default `3000k`). |
| `preset` | x264 preset for the combined stream (default `veryfast`). |
| `output_id` | HLS output folder/name under `/live/` (default `multiscreen`). |

### Defaults if a key is omitted

| Key | Default |
|-----|---------|
| `recordings_dir` | `../recordings` (relative to `config/`) |
| `hls_dir` | `../data/hls` |
| `recording_format` | `mpegts` |
| `segment_seconds` | `300` |
| `rtsp_transport` | `tcp` |
| `record` | `true` |
| `live` | `true` |
| `live_hls.segment_seconds` | `1.0` |
| `live_hls.list_size` | `6` |
| `live_hls.delete_threshold` | `1` |
| `live_hls.playlist_fresh_seconds` | `8.0` |
| `live_hls.target_latency_seconds` | `3.0` |
| `multiscreen.enabled` | `false` |
| `web.host` | `0.0.0.0` |
| `web.port` | `8765` |

### Recording layout

Files are written in **one directory per camera** (FFmpeg does not create nested date folders for `%Y-%m-%d` in the path).

```text
<recordings_dir>/<camera_id>/YYYY-MM-DD_HH-MM-SS.ts   # recording_format: mpegts
<recordings_dir>/<camera_id>/YYYY-MM-DD_HH-MM-SS.mp4  # recording_format: mp4
```

### Web API and live playback

- **`GET /`** — live dashboard (one tile per camera with `live: true`; includes a **Multiscreen** tile when multiscreen is active).
- **`GET /recordings`** — recordings browser (list by camera, inline play, download).
- **`GET /docs`** — interactive OpenAPI UI (FastAPI).
- **`GET /api/cameras`** — JSON list of cameras with `{id, name, enabled, record, live, hls_url, target_latency_seconds}`.
- **`GET /api/health`** — per-camera pipeline state: `running`, `uptime_s`, `restart_count`, `failure_streak`, `last_exit_code`, `last_error`, and `hls_playlist_age_s` / `hls_fresh` for quick external monitoring.
- **`GET /api/multiscreen`** — multiscreen config/runtime view: enabled/active state, selected camera IDs, output ID, and HLS URL.
- **`GET /api/recordings`** — summary: per-camera counts and total bytes.
- **`GET /api/recordings/{camera_id}?limit=&offset=`** — paginated list of recordings (newest first) with size, `mtime`, parsed `started_at`, and download URL.
- **`GET /recordings/{camera_id}/{filename}`** — serves a specific file (supports HTTP `Range`). Filenames and camera IDs are validated to prevent path traversal.

## Command line

```text
python3 -m nvr [-c CONFIG] [--record|--no-record] [--web|--no-web]
               [--host HOST] [--port PORT] [-v]
```

| Option | Meaning |
|--------|---------|
| `-c`, `--config` | Path to YAML. Default: **`config/cameras.yaml`** under the project root. |
| `--no-record` | Force-disable recording this run (overrides `record: true` in config). |
| `--record` | Force-enable recording this run (overrides `record: false` in config). |
| `--no-web` | Force-disable the web UI / HLS this run (overrides `live: true` in config). |
| `--web` | Force-enable the web UI / HLS this run (overrides `live: false` in config). |
| `--host` / `--port` | Override `web.host` / `web.port` from the config file. |
| `-v`, `--verbose` | Debug-level logging (FFmpeg stderr lines included). |

### Run modes

| Goal | Command or config |
|------|-------------------|
| Default (whatever config says) | `python3 -m nvr` |
| Persist "live-only" mode | set `record: false` in `cameras.yaml` |
| Persist "record-only" mode | set `live: false` in `cameras.yaml` |
| One-off live-only | `python3 -m nvr --no-record` |
| One-off record-only | `python3 -m nvr --no-web` |
| Force-enable recording for a test run | `python3 -m nvr --record` |
| Verbose logs | `python3 -m nvr -v` |
| Custom config path | `python3 -m nvr -c /etc/nvr/cameras.yaml` |

Per-camera `record: false` / `live: false` / `enabled: false` let you mix archive-only and live-only cameras in the same config.

## Live dashboard

Each tile has a colored status dot, refreshed every few seconds from `/api/health`:

| Dot | Meaning |
|-----|---------|
| Green | HLS pipeline running and producing recent segments. |
| Yellow (pulsing) | Pipeline restarting, stalled (no fresh segments), or still coming up. |
| Red | Permanently failed (e.g. wrong URL or credentials — check the logs). |
| Grey | Disabled for this camera. |

The line under each video shows the current state (`live: running`, `record: running`, playlist age) for quick at-a-glance diagnosis.

When `multiscreen.enabled: true` and at least one eligible live camera exists, the dashboard also shows a **Multiscreen** tile (fed by `/live/<output_id>/stream.m3u8`). Its status is derived from the same health model (`running`, `restarting`, `stalled`, `failed`) and playlist freshness checks.

### Live streaming tuning

Use the `live_hls` block to trade off latency vs stability:

```yaml
live_hls:
  segment_seconds: 1.0
  list_size: 6
  delete_threshold: 1
  playlist_fresh_seconds: 8.0
  target_latency_seconds: 3.0
```

- `segment_seconds` — lower values reduce latency but create more filesystem churn.
- `list_size` — number of segments exposed in the rolling playlist window.
- `delete_threshold` — extra old segments kept before FFmpeg deletion starts.
- `playlist_fresh_seconds` — threshold used by `/api/health` to classify stale HLS.
- `target_latency_seconds` — forwarded to the browser player (`hls.js`) live sync target.

For unstable links, raise `segment_seconds` (for example `1.5`-`2.0`) and `list_size` (`8`-`10`). For lowest possible latency on stable LAN streams, keep `segment_seconds: 1.0` with a small list (`5`-`6`).

## Recordings browser

`/recordings` lists cameras in the left rail (with recording count and total size) and the selected camera's clips on the right, newest first. Each row has a ▶ button for inline preview and a **Download** link. Pagination kicks in past 50 clips.

Empty state ("No recordings") is expected when `record: false` — enable recording to populate.

## Security

The dashboard, `/live/` URLs, recordings API, and recordings files are **unauthenticated**. Use only on a trusted network, set `web.host` to `127.0.0.1` for local-only access, or place a reverse proxy with authentication and TLS in front. If URLs contain passwords, restrict permissions on `config/cameras.yaml` (for example `chmod 600`) and prefer env-var interpolation via `.env` (see `.env.example`).

URL credentials are redacted from NVR's own logs, but FFmpeg's output (captured per-camera) may still mention the host/port — avoid sharing raw logs publicly.

## Audio

Recorder and HLS pipelines use **`-an`** (no audio). To record or stream audio, remove `-an` in `nvr/ffmpeg_common.py` (the shared preamble).

## Git and local data

`.gitignore` excludes **`config/cameras.yaml`** (secrets), **`.env`**, **`data/`**, contents of **`recordings/`** (except `recordings/.gitkeep`), `.venv/`, and common caches. Adjust if you want to track a non-secret config.

## Operational notes

- **Disk** — HLS keeps a short rolling window of segments; archived recordings grow with bitrate and time. Plan retention (a retention job is on the roadmap; for now, use cron/lifecycle rules).
- **Browser** — HLS uses codec copy; many desktops play H.264 in TS; **H.265/HEVC** in-browser is spotty outside Safari. Set **`hevc_tag: true`** for HEVC streams. Prefer the camera's H.264 substream for widest browser support, or accept transcoding (not included here).
- **Multiscreen CPU cost** — unlike per-camera copy-mode HLS, multiscreen decodes and re-encodes all included cameras into one canvas. Keep `fps`/tile size modest on low-power hosts.
- **Camera quirks** — If segments glitch or fail to open, test the same URL with the `ffmpeg` CLI (`-v` shows the captured stderr) and tune flags for that firmware.
- **Monitoring** — Hit `/api/health` from an external checker; `hls_fresh: false` or `pipelines.hls.state: "failed"` are the signals you care about.

## License

No license file is included. Add one if you distribute the project.
