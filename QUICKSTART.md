# Quick start

Minimal steps to run the live dashboard (and optionally record). Full detail: [README.md](README.md).

---

## 1. Install FFmpeg

**Debian / Ubuntu**

```bash
sudo apt update && sudo apt install -y ffmpeg
```

**Fedora**

```bash
sudo dnf install -y ffmpeg
```

Check:

```bash
ffmpeg -version
```

---

## 2. Python environment

Use the **NVR project root** — the folder that contains `nvr/` and `config/`.

```bash
cd /path/to/NVR
python3 -m venv .venv
```

Activate the venv:

- **Linux / macOS:** `source .venv/bin/activate`
- **Windows (cmd):** `.venv\Scripts\activate.bat`
- **Windows (PowerShell):** `.venv\Scripts\Activate.ps1`

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## 3. Configuration

```bash
cp config/cameras.example.yaml config/cameras.yaml
chmod 600 config/cameras.yaml
cp .env.example .env
chmod 600 .env
```

Edit **`config/cameras.yaml`**:

- Set each camera's **`url`** (usually `rtsp://…`). Use `${VAR}` for credentials and define the variables in `.env`.
- Give each camera a unique **`id`** matching `[A-Za-z0-9][A-Za-z0-9_-]*` (it's used as a directory name).
- **`recordings_dir`** / **`hls_dir`** paths are relative to the **`config/`** directory unless absolute.
- Use **`record`** / **`live`** (top-level or per-camera) to enable/disable each pipeline. `record: false` + `live: true` is the low-CPU live-only setup; the same effect is available one-off via `--no-record`.
- Tune live latency/stability with **`live_hls`** (`segment_seconds`, `list_size`, `delete_threshold`, `playlist_fresh_seconds`, `target_latency_seconds`).
- Optional: enable **`multiscreen`** to publish one combined live mosaic stream in parallel with normal per-camera streams.

Example (matches the template defaults):

```yaml
recordings_dir: ../recordings
hls_dir: ../data/hls
recording_format: mpegts
segment_seconds: 300
rtsp_transport: tcp

# Global toggles (per-camera overrides available below).
record: true
live: true

live_hls:
  segment_seconds: 1.0
  list_size: 6
  delete_threshold: 1
  playlist_fresh_seconds: 8.0
  target_latency_seconds: 3.0

web:
  host: "0.0.0.0"
  port: 8765

multiscreen:
  enabled: false
  # camera_ids: [front_door, garage]  # optional; defaults to all live-enabled cameras
  cols: 2
  tile_width: 640
  tile_height: 360
  fps: 10
  bitrate: 3000k
  preset: veryfast  # valid x264 presets: ultrafast..placebo
  output_id: multiscreen

cameras:
  - id: front_door
    name: Front door
    url: rtsp://${NVR_RTSP_USERNAME}:${NVR_CAM_FRONT_DOOR_PASSWORD}@192.168.1.50:554/stream1
    # hevc_tag: true  # for H.265 main streams (e.g. Hikvision ch101)
    # record: false   # live-only for this camera
    # live: false     # archive-only for this camera
```

With this layout, recordings land under **`recordings/<camera_id>/…`** (default **`.ts`** segments; see `recording_format` in [README.md](README.md)).

Fill in `.env`:

```
NVR_RTSP_USERNAME=admin
NVR_CAM_FRONT_DOOR_PASSWORD=...
```

---

## 4. Run the NVR

Stay in the project root, venv activated:

```bash
python3 -m nvr
```

By default this obeys the `record` / `live` settings in `cameras.yaml` (both `true` out of the box). Pass `--no-record` or `--no-web` for one-off overrides, or set them in the config to persist.

- **Dashboard:** [http://127.0.0.1:8765/](http://127.0.0.1:8765/) — live tiles with status dots
- **Recordings:** [http://127.0.0.1:8765/recordings](http://127.0.0.1:8765/recordings) — browse/play/download clips
- **Health:** [http://127.0.0.1:8765/api/health](http://127.0.0.1:8765/api/health) — per-camera state (JSON)
- **Multiscreen API (optional):** [http://127.0.0.1:8765/api/multiscreen](http://127.0.0.1:8765/api/multiscreen)
- **API docs:** [http://127.0.0.1:8765/docs](http://127.0.0.1:8765/docs)

If `web.host` is `0.0.0.0`, you can also open `http://<your-lan-ip>:8765/` from another device on the network.

If multiscreen is enabled, its HLS URL is:

- `http://127.0.0.1:8765/live/<output_id>/stream.m3u8` (default: `/live/multiscreen/stream.m3u8`)
- The dashboard automatically adds a **Multiscreen** tile when this stream is active.

Stop with **Ctrl+C**.

### Run modes

| Goal | How |
|------|-----|
| Default (from config) | `python3 -m nvr` |
| Persist "live-only" | set `record: false` in `cameras.yaml`, run normally |
| Persist "record-only" | set `live: false` in `cameras.yaml`, run normally |
| One-off live-only | `python3 -m nvr --no-record` |
| One-off record-only | `python3 -m nvr --no-web` |
| Force-enable recording for a test run | `python3 -m nvr --record` |
| Verbose logs (FFmpeg stderr included) | `python3 -m nvr -v` |
| Custom config path | `python3 -m nvr -c /etc/nvr/cameras.yaml` |
| Override listen port | `python3 -m nvr --port 9000` |

Per-camera `record` / `live` / `enabled` in the config let you mix live-only and record-only cameras in the same install.

---

## 5. Reading the UI

Each live tile has a status dot that polls `/api/health`:

- **Green** — HLS is running and segments are fresh.
- **Yellow (pulsing)** — starting up, restarting after a crash, or stalled (running but no fresh segments).
- **Red** — permanently failed after many consecutive immediate restarts (usually wrong URL or bad credentials — check logs).
- **Grey** — live disabled for this camera.

The line under each tile shows the per-pipeline state and the playlist age, so you can tell at a glance whether the source is healthy.

If multiscreen is enabled and active, it appears as its own tile at the top of the dashboard and follows the same status-dot behavior.

---

## 6. Troubleshooting

| Problem | What to try |
|---------|-------------|
| `Config not found` | Ensure `config/cameras.yaml` exists or pass `-c` to the real path. |
| `ffmpeg not found` | Install FFmpeg; run `which ffmpeg` and fix `PATH`. A red dot with `failed_permanently: true` also signals this. |
| Nothing to do: both recording and live are disabled | Set `record` or `live` to `true` in the config, or pass `--record` / `--web`. |
| `Missing or empty environment variable 'NVR_…'` | Create `.env` from `.env.example` and fill in the referenced variables. |
| Blank or frozen video tiles | Wait a few seconds for the first HLS segments; run with `-v` and check the per-camera FFmpeg lines (`nvr.ffmpeg.hls.<id>`); validate the RTSP URL with `ffplay` or `ffmpeg -i`. The status dot going yellow → green indicates progress. |
| Multiscreen stutters / high CPU | Lower `multiscreen.fps`, `tile_width`, `tile_height`, or bitrate; multiscreen re-encodes all included cameras. |
| Live feels too delayed / too jumpy | Tune `live_hls`: lower `segment_seconds`/`list_size` for less delay, or increase them for better stability on weak links. |
| Red dot immediately | Permanent failure after repeated sub-3s restarts. Open `/api/health`, read `last_error`. Common causes: wrong URL path, wrong password, unsupported transport. |
| `multiscreen.preset must be a valid x264 preset` | Fix `multiscreen.preset` (common typo: `veryfa#st`). Use one of `ultrafast`, `superfast`, `veryfast`, `faster`, `fast`, `medium`, `slow`, `slower`, `veryslow`, `placebo`. |
| `ModuleNotFoundError` / import errors | Run **`python3 -m nvr`** from the **project root**, not from inside the `nvr/` source folder. |
| Wrong recordings folder | Paths in YAML are relative to **`config/`** unless absolute; see [README.md](README.md). |
| HEVC / `hvc1` / blank HLS in Chrome | Set **`hevc_tag: true`** on that camera; for H.264 substreams remove it. HEVC in the browser may still need Safari or an H.264 URL. |
| `duplicate camera id` or `camera id '…' is not safe` | IDs must be unique and match `^[A-Za-z0-9][A-Za-z0-9_-]*$`. Rename in `cameras.yaml`. |
