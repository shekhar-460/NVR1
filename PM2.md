# Running NVR with PM2

[PM2](https://pm2.keymetrics.io/) keeps the NVR process running in the background, restarts it on crash, and can start it at boot. This project is **Python** (`python3 -m nvr`), not Node — PM2 supervises the venv interpreter directly.

Prerequisites: FFmpeg installed, venv created, dependencies installed, and `config/cameras.yaml` + `.env` configured. See [QUICKSTART.md](QUICKSTART.md) for the full setup.

---

## 1. Install PM2

Node.js/npm required:

```bash
npm install -g pm2
```

Verify:

```bash
pm2 -v
```

---

## 2. One-shot start

From the **project root** (the folder containing `nvr/` and `config/`):

```bash
cd /path/to/NVR

pm2 start .venv/bin/python3 \
  --name nvr \
  --cwd "$(pwd)" \
  --interpreter none \
  -- -m nvr
```

- **`--interpreter none`** — the “script” is already the Python binary; PM2 must not treat it as Node.
- **`--cwd`** — must be the project root so `config/cameras.yaml` and `.env` resolve correctly (`.env` is loaded automatically from the repo root).

Dashboard (default): [http://127.0.0.1:8765/](http://127.0.0.1:8765/) — port comes from `web.port` in `cameras.yaml`.

---

## 3. Ecosystem file (recommended)

Create **`ecosystem.config.cjs`** in the project root:

```javascript
module.exports = {
  apps: [
    {
      name: "nvr",
      cwd: "/path/to/NVR",           // ← change to your install path
      script: ".venv/bin/python3",
      args: ["-m", "nvr"],
      interpreter: "none",
      autorestart: true,
      max_restarts: 10,
      restart_delay: 5000,
      env: {
        PYTHONUNBUFFERED: "1",
      },
    },
  ],
};
```

Start:

```bash
cd /path/to/NVR
pm2 start ecosystem.config.cjs
pm2 save
```

Optional: enable start on boot (run the command PM2 prints):

```bash
pm2 startup
# then, as instructed:
pm2 save
```

---

## 4. CLI flags under PM2

Append flags to `args` in the ecosystem file, or after `--` on the command line.

| Goal | `args` example |
|------|----------------|
| Default (from `cameras.yaml`) | `["-m", "nvr"]` |
| Live-only (one-off) | `["-m", "nvr", "--no-record"]` |
| Record-only (one-off) | `["-m", "nvr", "--no-web"]` |
| Force recording on | `["-m", "nvr", "--record"]` |
| Verbose logs | `["-m", "nvr", "-v"]` |
| Custom config path | `["-m", "nvr", "-c", "/etc/nvr/cameras.yaml"]` |
| Override listen port | `["-m", "nvr", "--port", "9000"]` |

Example ecosystem snippet for live-only:

```javascript
args: ["-m", "nvr", "--no-record"],
```

After editing `ecosystem.config.cjs`:

```bash
pm2 reload ecosystem.config.cjs
# or
pm2 delete nvr && pm2 start ecosystem.config.cjs
```

---

## 5. Day-to-day commands

| Action | Command |
|--------|---------|
| Status | `pm2 status` |
| Logs (live) | `pm2 logs nvr` |
| Last 200 lines | `pm2 logs nvr --lines 200` |
| Restart | `pm2 restart nvr` |
| Stop (keep in list) | `pm2 stop nvr` |
| Remove from PM2 | `pm2 delete nvr` |
| Process details | `pm2 show nvr` |
| Flush log files | `pm2 flush nvr` |

PM2 does **not** replace application logs: FFmpeg stderr still goes to Python loggers (`nvr.ffmpeg.record.*`, `nvr.ffmpeg.hls.*`). Use `-v` / verbose mode for more detail in `pm2 logs`.

---

## 6. Updates and restarts

After pulling code or changing dependencies:

```bash
cd /path/to/NVR
source .venv/bin/activate
pip install -r requirements.txt
pm2 restart nvr
```

After editing `config/cameras.yaml` or `.env`:

```bash
pm2 restart nvr
```

Some YAML changes (camera list, URLs) are picked up on restart; the running process does not hot-reload config.

---

## 7. Troubleshooting

| Problem | What to check |
|---------|----------------|
| `Config not found` | `cwd` in PM2 must be the project root, or pass `-c` with an absolute path in `args`. |
| `ffmpeg not found` | FFmpeg on `PATH` for the user running PM2 (often your login user, not root). |
| `ModuleNotFoundError` | `script` must point to **`.venv/bin/python3`**, not system `python3`. |
| Missing `NVR_…` env vars | `.env` in project root; PM2 `cwd` must be that root. |
| Port already in use | Another `nvr` instance or service on `web.port`; `pm2 delete nvr` or change port in YAML / `--port`. |
| Blank dashboard / red dots | Same as [QUICKSTART.md § Troubleshooting](QUICKSTART.md#6-troubleshooting); check `pm2 logs nvr` and `/api/health`. |
| High CPU / RAM | Consider `record: false` (live-only) in config; fewer cameras; lower multiscreen settings. |

---

## 8. systemd alternative

On Linux servers without Node/PM2, a **systemd** unit is equally common: one `ExecStart` pointing at `.venv/bin/python3 -m nvr` with `WorkingDirectory` set to the project root. PM2 is optional convenience if you already use it for other services.
