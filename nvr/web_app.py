from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from nvr import __version__
from nvr.recordings import (
    CONTENT_TYPES,
    list_recordings,
    resolve_recording,
    summarize_all,
)
from nvr.settings import Camera, Settings
from nvr.state import REGISTRY


def _playlist_mtime(hls_dir: Path, cam_id: str) -> float | None:
    try:
        st = (hls_dir / cam_id / "stream.m3u8").stat()
    except FileNotFoundError:
        return None
    except OSError:
        return None
    return st.st_mtime


def _camera_public(cam: Camera, settings: Settings) -> dict[str, Any]:
    return {
        "id": cam.id,
        "name": cam.name,
        "enabled": cam.enabled,
        "record": settings.should_record(cam),
        "live": settings.should_live(cam),
        "hls_url": f"/live/{cam.id}/stream.m3u8" if settings.should_live(cam) else None,
    }


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="NVR", version=__version__)
    app.state.settings = settings
    static_dir = Path(__file__).resolve().parent / "static"

    @app.get("/api/cameras")
    def list_cameras() -> JSONResponse:
        s: Settings = app.state.settings
        return JSONResponse([_camera_public(c, s) for c in s.cameras])

    @app.get("/api/health")
    def health() -> JSONResponse:
        s: Settings = app.state.settings
        now = time.time()
        statuses = {
            (item["camera_id"], item["role"]): item for item in REGISTRY.snapshot()
        }
        out: list[dict[str, Any]] = []
        for cam in s.cameras:
            entry: dict[str, Any] = {
                "id": cam.id,
                "name": cam.name,
                "enabled": cam.enabled,
                "pipelines": {},
            }
            for role in ("record", "hls"):
                wanted = (
                    s.should_record(cam) if role == "record" else s.should_live(cam)
                )
                status = statuses.get((cam.id, role))
                if status is None:
                    entry["pipelines"][role] = {
                        "configured": wanted,
                        "running": False,
                        "state": "disabled" if not wanted else "pending",
                    }
                    continue
                slim = {k: v for k, v in status.items() if k not in ("camera_id", "role")}
                entry["pipelines"][role] = {
                    "configured": wanted,
                    **slim,
                    "state": _derive_state(status, wanted),
                }
            if s.should_live(cam):
                mtime = _playlist_mtime(s.hls_dir, cam.id)
                entry["hls_playlist_age_s"] = None if mtime is None else max(0.0, now - mtime)
                entry["hls_fresh"] = (
                    mtime is not None and (now - mtime) < 10.0
                )
            out.append(entry)
        return JSONResponse(
            {
                "server_time": now,
                "version": __version__,
                "cameras": out,
            }
        )

    @app.get("/api/recordings")
    def recordings_summary() -> JSONResponse:
        s: Settings = app.state.settings
        return JSONResponse(summarize_all(s))

    @app.get("/api/recordings/{camera_id}")
    def recordings_for_camera(
        camera_id: str,
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
    ) -> JSONResponse:
        s: Settings = app.state.settings
        if camera_id not in {c.id for c in s.cameras}:
            raise HTTPException(status_code=404, detail="camera not found")
        return JSONResponse(list_recordings(s, camera_id, limit=limit, offset=offset))

    @app.get("/recordings/{camera_id}/{filename}")
    def download_recording(camera_id: str, filename: str) -> FileResponse:
        s: Settings = app.state.settings
        path = resolve_recording(s, camera_id, filename)
        if path is None:
            raise HTTPException(status_code=404, detail="recording not found")
        media_type = CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")
        return FileResponse(path, media_type=media_type, filename=path.name)

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/recordings")
    def recordings_page() -> FileResponse:
        return FileResponse(static_dir / "recordings.html")

    app.mount(
        "/css",
        StaticFiles(directory=str(static_dir / "css")),
        name="css",
    )
    app.mount(
        "/js",
        StaticFiles(directory=str(static_dir / "js")),
        name="js",
    )
    hls_root = settings.hls_dir.resolve()
    app.mount("/live", StaticFiles(directory=str(hls_root)), name="live")
    return app


def _derive_state(status: dict[str, Any], wanted: bool) -> str:
    if not wanted:
        return "disabled"
    if status.get("failed_permanently"):
        return "failed"
    if status.get("running"):
        return "running"
    streak = int(status.get("failure_streak") or 0)
    if streak > 0:
        return "restarting"
    return "pending"
