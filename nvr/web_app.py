from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from nvr import __version__
from nvr.multiscreen import selected_multiscreen_cameras
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


def _multiscreen_public(settings: Settings) -> dict[str, Any]:
    ms = settings.multiscreen
    cams = selected_multiscreen_cameras(settings)
    active = settings.live and ms.enabled and len(cams) > 0
    return {
        "enabled": ms.enabled,
        "active": active,
        "output_id": ms.output_id,
        "camera_ids": [cam.id for cam in cams],
        "hls_url": f"/live/{ms.output_id}/stream.m3u8" if active else None,
    }


def _multiscreen_health(settings: Settings, now: float, statuses: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any]:
    base = _multiscreen_public(settings)
    if not base["active"]:
        base["pipeline"] = {
            "configured": False,
            "running": False,
            "state": "disabled",
        }
        base["hls_playlist_age_s"] = None
        base["hls_fresh"] = False
        return base
    status = statuses.get((base["output_id"], "hls"))
    if status is None:
        base["pipeline"] = {
            "configured": True,
            "running": False,
            "state": "pending",
        }
    else:
        slim = {k: v for k, v in status.items() if k not in ("camera_id", "role")}
        base["pipeline"] = {
            "configured": True,
            **slim,
            "state": _derive_state(status, True),
        }
    mtime = _playlist_mtime(settings.hls_dir, str(base["output_id"]))
    base["hls_playlist_age_s"] = None if mtime is None else max(0.0, now - mtime)
    base["hls_fresh"] = mtime is not None and (now - mtime) < 10.0
    return base


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="NVR", version=__version__)
    app.state.settings = settings
    static_dir = Path(__file__).resolve().parent / "static"

    @app.get("/api/cameras")
    def list_cameras() -> JSONResponse:
        s: Settings = app.state.settings
        return JSONResponse([_camera_public(c, s) for c in s.cameras])

    @app.get("/api/multiscreen")
    def multiscreen_info() -> JSONResponse:
        s: Settings = app.state.settings
        statuses = {
            (item["camera_id"], item["role"]): item for item in REGISTRY.snapshot()
        }
        return JSONResponse(_multiscreen_health(s, time.time(), statuses))

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
                "multiscreen": _multiscreen_health(s, now, statuses),
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

    @app.get("/live/{camera_id}/{filename}")
    def live_hls(camera_id: str, filename: str) -> Response:
        # HLS files (.m3u8 / .ts) are actively being written by FFmpeg, so the
        # file size can grow between a stat() and the actual read. StaticFiles
        # precomputes Content-Length from stat() which then mismatches the
        # streamed bytes and raises "Response content longer than Content-Length".
        # Read the whole file into memory and let Starlette set an exact length.
        if "/" in camera_id or "\\" in camera_id or camera_id in ("", ".", ".."):
            raise HTTPException(status_code=404, detail="not found")
        if "/" in filename or "\\" in filename or filename in ("", ".", ".."):
            raise HTTPException(status_code=404, detail="not found")
        path = (hls_root / camera_id / filename).resolve()
        try:
            path.relative_to(hls_root)
        except ValueError:
            raise HTTPException(status_code=404, detail="not found")
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="not found")
        except OSError:
            raise HTTPException(status_code=404, detail="not found")
        suffix = path.suffix.lower()
        if suffix == ".m3u8":
            media_type = "application/vnd.apple.mpegurl"
        elif suffix == ".ts":
            media_type = "video/mp2t"
        elif suffix == ".m4s" or suffix == ".mp4":
            media_type = "video/mp4"
        else:
            media_type = "application/octet-stream"
        headers = {"Cache-Control": "no-store"}
        return Response(content=data, media_type=media_type, headers=headers)

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
