from __future__ import annotations

import argparse
import logging
import re
import signal
import sys
import threading
from pathlib import Path

import uvicorn

from nvr.hls_live import ensure_hls_tree, run_camera_hls
from nvr.recorder import ensure_recording_tree, run_camera_recorder
from nvr.settings import Settings, default_config_path, load_settings
from nvr.web_app import create_app

log = logging.getLogger("nvr")

_URL_CREDS = re.compile(r"(://)([^/@\s]+)@")


class _RedactingFilter(logging.Filter):
    """Strip ``user:password@`` from any log message before emission."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        if "@" in msg and "://" in msg:
            record.msg = _URL_CREDS.sub(r"\1***@", msg)
            record.args = ()
        return True


def _run_uvicorn(settings: Settings, server_box: list[uvicorn.Server]) -> None:
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
        help="Do not write segmented recordings (overrides config 'record: true').",
    )
    parser.add_argument(
        "--record",
        action="store_true",
        help="Force-enable recording (overrides config 'record: false').",
    )
    parser.add_argument(
        "--no-web",
        action="store_true",
        help="Do not start the web UI or HLS transcoders (overrides config 'live: true').",
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="Force-enable the web UI / HLS (overrides config 'live: false').",
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
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.getLogger().addFilter(_RedactingFilter())

    if args.no_record and args.record:
        log.error("--record and --no-record are mutually exclusive.")
        sys.exit(2)
    if args.no_web and args.web:
        log.error("--web and --no-web are mutually exclusive.")
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

    if args.record:
        settings.record = True
    elif args.no_record:
        settings.record = False
    if args.web:
        settings.live = True
    elif args.no_web:
        settings.live = False

    record_any = settings.record and any(settings.should_record(c) for c in settings.cameras)
    live_any = settings.live and any(settings.should_live(c) for c in settings.cameras)
    if not record_any and not live_any:
        log.error(
            "Nothing to do: both recording and live are disabled (check config and flags)."
        )
        sys.exit(2)

    stop = threading.Event()
    server_box: list[uvicorn.Server] = []

    def handle_sig(_signum: int, _frame: object) -> None:
        if not stop.is_set():
            log.info("Shutting down…")
        stop.set()
        if server_box:
            server_box[0].should_exit = True

    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)

    ffmpeg_threads: list[threading.Thread] = []
    if record_any:
        ensure_recording_tree(settings)
        for cam in settings.cameras:
            if not settings.should_record(cam):
                log.info("Recording disabled for %s (%s)", cam.name, cam.id)
                continue
            t = threading.Thread(
                target=run_camera_recorder,
                args=(cam, settings, stop),
                name=f"record-{cam.id}",
                daemon=False,
            )
            ffmpeg_threads.append(t)
    if live_any:
        ensure_hls_tree(settings)
        for cam in settings.cameras:
            if not settings.should_live(cam):
                log.info("Live/HLS disabled for %s (%s)", cam.name, cam.id)
                continue
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
    if live_any:
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
        while not stop.is_set():
            stop.wait(1.0)
    except KeyboardInterrupt:
        stop.set()

    if server_box:
        server_box[0].should_exit = True
    for t in ffmpeg_threads:
        t.join(timeout=120)
    if uv_thread is not None:
        uv_thread.join(timeout=60)


if __name__ == "__main__":
    main()
