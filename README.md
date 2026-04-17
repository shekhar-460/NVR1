# NVR

Multi-camera IP CCTV recorder with a **browser dashboard** for live viewing. Recordings use [FFmpeg](https://ffmpeg.org/)’s segment muxer (MP4 on disk). Live view runs **one FFmpeg process per camera** to publish **HLS** (`stream.m3u8` + MPEG-TS segments). Browsers play that stream with [hls.js](https://github.com/video-dev/hls.js/) (or Safari’s native HLS).

## Features

- **Multiple streams** — separate supervisor loop per camera; one camera failing does not stop the others.
- **Disk recording** — time-segmented MP4s under a configurable root (`-c copy`, low CPU when the source is already H.264).
- **Web UI** — responsive grid of live tiles; [FastAPI](https://fastapi.tiangolo.com/) serves the app and static HLS under `/live/…`.
- **Automatic FFmpeg restart** — exponential backoff (capped at 60 seconds) after an unexpected exit.
- **Clean shutdown** — SIGINT / SIGTERM stops FFmpeg children and the web server.

### Process model (default)

With **recording and web both enabled** (the default), each camera runs **two** FFmpeg processes: one for MP4 segments and one for HLS. That roughly doubles network and CPU use versus **record-only** (`--no-web`). Use `--no-record` if you only need the dashboard.

## Requirements

- **Python** 3.10+
- **FFmpeg** on your `PATH`
- **Python packages** in `requirements.txt`: PyYAML, FastAPI, Uvicorn

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
    supervisor.py
    recorder.py
    hls_live.py
    web_app.py
    static/
      index.html
      css/main.css
      js/app.js
  recordings/           # MP4 archive; contents gitignored; .gitkeep kept
  data/                 # HLS cache for live view (gitignored)
  requirements.txt
  README.md
  QUICKSTART.md
  .gitignore
```

Run from the **repository root** (the directory that contains the `nvr` package):

```bash
python3 -m nvr
```

## Configuration

Copy `config/cameras.example.yaml` to `config/cameras.yaml`.

**Relative paths** in the YAML (`recordings_dir`, `hls_dir`) are resolved against the **directory that contains the config file** (i.e. `config/`). Example: `../recordings` → `NVR/recordings/`, `../data/hls` → `NVR/data/hls/`.

| Key | Description |
|-----|-------------|
| `recordings_dir` | Root directory for MP4 segments. |
| `hls_dir` | Root for HLS playlists and `.ts` files (exposed as `/live/<camera_id>/…`). |
| `recording_format` | `mpegts` (default) writes `.ts` segments; `mp4` writes `.mp4`. MPEG-TS is more reliable for **codec copy** with H.264/H.265 from RTSP. |
| `segment_seconds` | Recording segment length in seconds (minimum **30** enforced in code). |
| `rtsp_transport` | FFmpeg `-rtsp_transport` (`tcp` by default). |
| `web.host` / `web.port` | HTTP bind address and port (`0.0.0.0` and **8765** by default). |
| `cameras` | List of cameras: **`url`** (required), **`id`**, **`name`**, optional **`hevc_tag`** (`true` adds `-tag:v hvc1` for H.265 in MP4/HLS; omit for H.264-only). |

### Defaults if a key is omitted

| Key | Default |
|-----|---------|
| `recordings_dir` | `../recordings` (relative to `config/`) |
| `hls_dir` | `../data/hls` |
| `recording_format` | `mpegts` |
| `segment_seconds` | `300` |
| `rtsp_transport` | `tcp` |
| `web.host` | `0.0.0.0` |
| `web.port` | `8765` |

### Recording layout

Files are written in **one directory per camera** (FFmpeg does not create nested date folders for `%Y-%m-%d` in the path).

```text
<recordings_dir>/<camera_id>/YYYY-MM-DD_HH-MM-SS.ts   # recording_format: mpegts
<recordings_dir>/<camera_id>/YYYY-MM-DD_HH-MM-SS.mp4  # recording_format: mp4
```

### Web API and live playback

- **`GET /api/cameras`** — JSON list of cameras with `id`, `name`, and `hls_url` (e.g. `/live/<id>/stream.m3u8`).
- **`GET /docs`** — interactive OpenAPI UI (FastAPI).
- The dashboard at **`/`** loads hls.js from a CDN and attaches one player per camera.

## Command line

```text
python3 -m nvr [-c CONFIG] [--no-record] [--no-web] [--host HOST] [--port PORT] [-v]
```

| Option | Meaning |
|--------|---------|
| `-c`, `--config` | Path to YAML. Default: **`config/cameras.yaml`** under the project root (same level as the `nvr` folder). |
| `--no-record` | Web UI + HLS only; no MP4 archiving. |
| `--no-web` | MP4 recording only; no HTTP server and no HLS processes. |
| `--host` / `--port` | Override `web.host` / `web.port` from the config file. |
| `-v`, `--verbose` | Debug-level logging. |

## Security

The dashboard and `/live/` URLs are **unauthenticated**. Use only on a trusted network, set `web.host` to `127.0.0.1` for local-only access, or place a reverse proxy with authentication and TLS in front. If URLs contain passwords, restrict permissions on `config/cameras.yaml` (for example `chmod 600`).

## Audio

Recorder and HLS pipelines use **`-an`** (no audio). To record or stream audio, remove `-an` in `nvr/recorder.py` and `nvr/hls_live.py`.

## Git and local data

`.gitignore` excludes **`config/cameras.yaml`** (secrets), **`data/`**, contents of **`recordings/`** (except `recordings/.gitkeep`), `.venv/`, and common caches. Adjust if you want to track a non-secret config.

## Operational notes

- **Disk** — HLS keeps a short rolling window of segments; MP4 archives grow with bitrate and time. Plan retention (cron, lifecycle rules, etc.).
- **Browser** — HLS uses codec copy; many desktops play H.264 in TS; **H.265/HEVC** in-browser is spotty outside Safari. Set **`hevc_tag: true`** for HEVC streams (see config). Prefer the camera’s H.264 substream for widest browser support, or accept transcoding (not included here).
- **Camera quirks** — If segments glitch or fail to open, test the same URL with the `ffmpeg` CLI and tune flags for that firmware.

## License

No license file is included. Add one if you distribute the project.
