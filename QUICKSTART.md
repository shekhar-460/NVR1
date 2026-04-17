# Quick start

Minimal steps to record cameras and open the live dashboard. Full detail: [README.md](README.md).

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
```

Edit **`config/cameras.yaml`**:

- Set each **`url`** (usually `rtsp://…`).
- Give each camera a unique **`id`** (folder name under `recordings_dir` and under `hls_dir`).
- **`recordings_dir`** / **`hls_dir`** paths are relative to the **`config/`** directory unless you use an absolute path.

Example (matches the template defaults):

```yaml
recordings_dir: ../recordings
hls_dir: ../data/hls
recording_format: mpegts
segment_seconds: 300
rtsp_transport: tcp

web:
  host: "0.0.0.0"
  port: 8765

cameras:
  - id: front
    name: Front door
    url: rtsp://user:password@192.168.1.50:554/stream1
    # hevc_tag: true # use for H.265 main streams (e.g. Hikvision ch101)
```

With this layout, recordings land under **`recordings/<camera_id>/…`** (default **`.ts`** segments; see `recording_format` in [README.md](README.md)).

---

## 4. Run the NVR

Stay in the project root, venv activated:

```bash
python3 -m nvr
```

By default this starts **both** MP4 recording and the **web UI** (with HLS transcoders).

- **Dashboard:** [http://127.0.0.1:8765/](http://127.0.0.1:8765/)
- **API docs:** [http://127.0.0.1:8765/docs](http://127.0.0.1:8765/docs)

If `web.host` is `0.0.0.0`, you can also open `http://<your-lan-ip>:8765/` from another device on the network.

Stop with **Ctrl+C**.

### Run modes

| Goal | Command |
|------|---------|
| Default (record + live web) | `python3 -m nvr` |
| Record only (no HTTP / HLS) | `python3 -m nvr --no-web` |
| Live web only (no MP4 archive) | `python3 -m nvr --no-record` |
| Verbose logs | `python3 -m nvr -v` |
| Custom config path | `python3 -m nvr -c /etc/nvr/cameras.yaml` |
| Override port | `python3 -m nvr --port 9000` |

---

## 5. Troubleshooting

| Problem | What to try |
|---------|-------------|
| `Config not found` | Ensure `config/cameras.yaml` exists or pass `-c` to the real path. |
| `ffmpeg not found` | Install FFmpeg; run `which ffmpeg` (Linux/macOS) and fix `PATH`. |
| Blank or frozen video tiles | Wait a few seconds for the first HLS segments; run with `-v` and check FFmpeg lines; validate the RTSP URL with `ffplay` or `ffmpeg -i`. |
| `ModuleNotFoundError` / import errors | Run **`python3 -m nvr`** from the **project root**, not from inside the `nvr/` source folder. |
| Wrong recordings folder | Remember paths in YAML are relative to **`config/`** unless absolute; see [README.md](README.md). |
| `Failed to open segment` / `No such file or directory` | Fixed in current versions by flat filenames under each camera dir. Upgrade and set `recording_format: mpegts` if MP4/HEVC still misbehaves. |
| HEVC / `hvc1` / blank HLS in Chrome | Set **`hevc_tag: true`** on that camera; for H.264 substreams remove it. HEVC in the browser may still need Safari or an H.264 URL. |
