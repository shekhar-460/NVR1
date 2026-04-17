"""File-system helpers for listing and serving recorded segments."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from nvr.settings import Settings

_RECORDING_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})\.(ts|mp4)$")
_ALLOWED_EXTS = {".ts", ".mp4"}

CONTENT_TYPES = {
    ".ts": "video/mp2t",
    ".mp4": "video/mp4",
}


def camera_recording_dir(settings: Settings, cam_id: str) -> Path | None:
    """Return the (validated) directory for ``cam_id``'s recordings, or None."""
    if cam_id not in {c.id for c in settings.cameras}:
        return None
    root = settings.recordings_dir.resolve()
    target = (root / cam_id).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return None
    return target


def _parse_started_at(stem: str) -> float | None:
    try:
        return datetime.strptime(stem, "%Y-%m-%d_%H-%M-%S").timestamp()
    except ValueError:
        return None


def list_recordings(
    settings: Settings,
    cam_id: str,
    *,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    limit = max(1, min(limit, 1000))
    offset = max(0, offset)
    cam_dir = camera_recording_dir(settings, cam_id)
    if cam_dir is None or not cam_dir.is_dir():
        return {"camera_id": cam_id, "total": 0, "items": []}
    entries: list[tuple[Path, float]] = []
    for entry in cam_dir.iterdir():
        if not entry.is_file() or entry.suffix.lower() not in _ALLOWED_EXTS:
            continue
        m = _RECORDING_NAME.match(entry.name)
        if not m:
            continue
        try:
            mtime = entry.stat().st_mtime
        except OSError:
            continue
        entries.append((entry, mtime))
    entries.sort(key=lambda p: p[1], reverse=True)
    total = len(entries)
    window = entries[offset : offset + limit]
    items: list[dict[str, Any]] = []
    for path, mtime in window:
        m = _RECORDING_NAME.match(path.name)
        assert m is not None
        started = _parse_started_at(m.group(1))
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        items.append(
            {
                "filename": path.name,
                "size_bytes": size,
                "mtime": mtime,
                "started_at": started,
                "url": f"/recordings/{cam_id}/{path.name}",
            }
        )
    return {
        "camera_id": cam_id,
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": items,
    }


def summarize_all(settings: Settings) -> dict[str, Any]:
    cams: list[dict[str, Any]] = []
    grand_total = 0
    grand_bytes = 0
    for cam in settings.cameras:
        cam_dir = camera_recording_dir(settings, cam.id)
        count = 0
        size = 0
        newest: float | None = None
        if cam_dir is not None and cam_dir.is_dir():
            for entry in cam_dir.iterdir():
                if not entry.is_file() or entry.suffix.lower() not in _ALLOWED_EXTS:
                    continue
                if not _RECORDING_NAME.match(entry.name):
                    continue
                try:
                    st = entry.stat()
                except OSError:
                    continue
                count += 1
                size += st.st_size
                if newest is None or st.st_mtime > newest:
                    newest = st.st_mtime
        grand_total += count
        grand_bytes += size
        cams.append(
            {
                "id": cam.id,
                "name": cam.name,
                "count": count,
                "size_bytes": size,
                "newest_mtime": newest,
            }
        )
    return {
        "total_recordings": grand_total,
        "total_bytes": grand_bytes,
        "cameras": cams,
    }


def resolve_recording(settings: Settings, cam_id: str, filename: str) -> Path | None:
    """Safely resolve a camera/filename pair to an on-disk recording."""
    if not _RECORDING_NAME.match(filename):
        return None
    cam_dir = camera_recording_dir(settings, cam_id)
    if cam_dir is None:
        return None
    candidate = (cam_dir / filename).resolve()
    try:
        candidate.relative_to(cam_dir)
    except ValueError:
        return None
    if not candidate.is_file():
        return None
    return candidate
