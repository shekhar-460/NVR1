from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from nvr.settings import Settings


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="NVR", version="0.2.0")
    app.state.settings = settings
    static_dir = Path(__file__).resolve().parent / "static"

    @app.get("/api/cameras")
    def list_cameras() -> JSONResponse:
        s: Settings = app.state.settings
        payload = [
            {
                "id": c.id,
                "name": c.name,
                "hls_url": f"/live/{c.id}/stream.m3u8",
            }
            for c in s.cameras
        ]
        return JSONResponse(payload)

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

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
