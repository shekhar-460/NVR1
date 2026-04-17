from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
import time
from pathlib import Path

import uvicorn

from nvr.hls_live import ensure_hls_tree, run_camera_hls
from nvr.recorder import ensure_recording_tree, run_camera_recorder
from nvr.settings import Settings, default_config_path, load_settings
from nvr.web_app import create_app

log = logging.getLogger("nvr")


def _run_uvicorn(settings: Settings, server_box: list) -> None:
    app = create_app(settings)
    config = uvicorn.Config(
        app,
        host=settings.web.host,
        port=settings.web.port,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    server_box.append(server)
    server.run()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Multi-camera NVR: record to disk and/or live view in the browser (HLS).",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=default_config_path(),
        help="Path to cameras.yaml",
    )
    parser.add_argument(
        "--no-record",
        action="store_true",
        help="Do not write segmented MP4 recordings (live web only).",
    )
    parser.add_argument(
        "--no-web",
        action="store_true",
        help="Do not start the web UI or HLS transcoders (record only).",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Override web listen address (default: from config).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Override web port (default: from config).",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    if args.no_record and args.no_web:
        log.error("Choose at least one of recording or web (remove --no-record or --no-web).")
        sys.exit(2)
    if not args.config.is_file():
        log.error(
            "Config not found: %s (copy config/cameras.example.yaml to config/cameras.yaml)",
            args.config,
        )
        sys.exit(1)
    settings = load_settings(args.config)
    if args.host is not None:
        settings.web.host = args.host
    if args.port is not None:
        settings.web.port = args.port

    stop: list[bool] = [False]
    server_box: list = []

    def handle_sig(_signum, _frame) -> None:
        log.info("Shutting down…")
        stop[0] = True

    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)

    ffmpeg_threads: list[threading.Thread] = []
    if not args.no_record:
        ensure_recording_tree(settings)
        for cam in settings.cameras:
            t = threading.Thread(
                target=run_camera_recorder,
                args=(cam, settings, stop),
                name=f"record-{cam.id}",
                daemon=False,
            )
            ffmpeg_threads.append(t)
    if not args.no_web:
        ensure_hls_tree(settings)
        for cam in settings.cameras:
            t = threading.Thread(
                target=run_camera_hls,
                args=(cam, settings, stop),
                name=f"hls-{cam.id}",
                daemon=False,
            )
            ffmpeg_threads.append(t)

    for t in ffmpeg_threads:
        t.start()

    uv_thread: threading.Thread | None = None
    if not args.no_web:
        uv_thread = threading.Thread(
            target=_run_uvicorn,
            args=(settings, server_box),
            name="uvicorn",
            daemon=False,
        )
        uv_thread.start()
        log.info(
            "Web UI: http://%s:%s/",
            settings.web.host if settings.web.host != "0.0.0.0" else "127.0.0.1",
            settings.web.port,
        )
        if settings.web.host == "0.0.0.0":
            log.info("Listening on all interfaces; use your LAN IP to open from other devices.")

    try:
        while not stop[0]:
            time.sleep(0.5)
    except KeyboardInterrupt:
        stop[0] = True

    if server_box:
        server_box[0].should_exit = True
    for t in ffmpeg_threads:
        t.join(timeout=120)
    if uv_thread is not None:
        uv_thread.join(timeout=60)


if __name__ == "__main__":
    main()
