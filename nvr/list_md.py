from __future__ import annotations

import logging
import socket
from pathlib import Path

from nvr.multiscreen import selected_multiscreen_cameras
from nvr.settings import Camera, Settings

log = logging.getLogger("nvr")


def detect_public_host() -> str:
    """Best-effort LAN address for URLs shown to other devices on the network."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def public_base_url(settings: Settings) -> str:
    host = settings.web.public_host or detect_public_host()
    return f"http://{host}:{settings.web.port}"


def _live_cameras(settings: Settings) -> list[Camera]:
    return [cam for cam in settings.cameras if settings.should_live(cam)]


def write_list_md(settings: Settings, config_path: Path) -> Path:
    """Regenerate LIST.md from the loaded config (enabled live cameras + multiscreen)."""
    repo_root = config_path.resolve().parent.parent
    out = repo_root / "LIST.md"
    base = public_base_url(settings)
    live = _live_cameras(settings)
    ms = settings.multiscreen
    ms_cams = selected_multiscreen_cameras(settings)
    ms_active = settings.live and ms.enabled and len(ms_cams) > 0

    lines = [
        "# Individual streams",
        "",
        "Auto-generated on NVR startup from `config/cameras.yaml`.",
        "",
        f"**Host:** `{base.replace('http://', '')}`",
        "",
    ]

    if live:
        lines.append("## Browser — single camera view")
        lines.append("")
        for cam in live:
            lines.append(f"{base}/cam/{cam.id}")
        lines.append("")
        lines.append("## HLS playlist (VLC, players, embed)")
        lines.append("")
        for cam in live:
            lines.append(f"{base}/live/{cam.id}/stream.m3u8")
        lines.append("")
    else:
        lines.append("_No live cameras enabled._")
        lines.append("")

    if ms_active:
        lines.append("## Multiscreen")
        lines.append("")
        lines.append(f"{base}/live/{ms.output_id}/stream.m3u8")
        lines.append("")

    lines.append("## All cameras grid")
    lines.append("")
    lines.append(f"{base}/")
    lines.append("")

    out.write_text("\n".join(lines), encoding="utf-8")
    log.info("Wrote %s (%d live camera(s)%s)", out, len(live), ", multiscreen" if ms_active else "")
    return out


def log_startup_plan(settings: Settings) -> None:
    """Log which pipelines will start for this run."""
    live = _live_cameras(settings)
    record = [c for c in settings.cameras if settings.should_record(c)]
    ms = settings.multiscreen
    ms_cams = selected_multiscreen_cameras(settings)
    ms_active = settings.live and ms.enabled and len(ms_cams) > 0

    log.info(
        "Config: %d camera(s) defined, %d live, %d record",
        len(settings.cameras),
        len(live),
        len(record),
    )
    for cam in settings.cameras:
        if not cam.enabled:
            log.info("  skipped (enabled=false): %s (%s)", cam.name, cam.id)
            continue
        roles: list[str] = []
        if settings.should_record(cam):
            roles.append("record")
        if settings.should_live(cam):
            roles.append("live")
        if roles:
            log.info("  %s: %s (%s)", " + ".join(roles), cam.name, cam.id)
        else:
            log.info("  skipped (record and live off): %s (%s)", cam.name, cam.id)

    if ms.enabled:
        if ms_active:
            ids = ", ".join(c.id for c in ms_cams)
            log.info("  multiscreen: on (%s) → /live/%s/stream.m3u8", ids, ms.output_id)
        else:
            log.info("  multiscreen: enabled in config but no eligible live cameras")
    else:
        log.info("  multiscreen: off")
