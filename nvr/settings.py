from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

_ENV_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]*$")


@dataclass
class Camera:
    id: str
    name: str
    url: str
    # H.265/HEVC in MP4 or HLS often needs -tag:v hvc1 (omit for H.264-only cameras).
    hevc_tag: bool = False
    # Per-camera overrides of the global record/live toggles. None means "use global".
    record: bool | None = None
    live: bool | None = None
    enabled: bool = True


@dataclass
class WebSettings:
    host: str
    port: int


@dataclass
class MultiScreenSettings:
    enabled: bool = False
    camera_ids: list[str] = field(default_factory=list)
    cols: int = 2
    tile_width: int = 640
    tile_height: int = 360
    fps: int = 10
    bitrate: str = "3000k"
    preset: str = "veryfast"
    output_id: str = "multiscreen"


@dataclass
class Settings:
    recordings_dir: Path
    hls_dir: Path
    segment_seconds: int
    rtsp_transport: str
    # mpegts = .ts chunks (robust for H.264/H.265 copy); mp4 = .mp4 (fine for many H.264 cams).
    recording_format: str
    cameras: list[Camera]
    web: WebSettings
    # Global defaults. Per-camera ``record`` / ``live`` override these when set.
    record: bool = True
    live: bool = True
    multiscreen: MultiScreenSettings = field(default_factory=MultiScreenSettings)
    extras: dict[str, Any] = field(default_factory=dict)

    def should_record(self, cam: Camera) -> bool:
        if not cam.enabled:
            return False
        return cam.record if cam.record is not None else self.record

    def should_live(self, cam: Camera) -> bool:
        if not cam.enabled:
            return False
        return cam.live if cam.live is not None else self.live


def default_config_path() -> Path:
    return Path(__file__).resolve().parent.parent / "config" / "cameras.yaml"


def _expand_env_in_str(value: str, *, context: str) -> str:
    def replace(m: re.Match[str]) -> str:
        key = m.group(1)
        if key not in os.environ or os.environ[key] == "":
            raise SystemExit(
                f"Missing or empty environment variable {key!r} "
                f"(set it in .env or the environment; used in {context})"
            )
        return os.environ[key]

    return _ENV_REF.sub(replace, value)


def _as_bool(value: Any, key: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "yes", "on", "1"):
            return True
        if lowered in ("false", "no", "off", "0"):
            return False
    raise SystemExit(f"{key}: expected a boolean (true/false), got {value!r}")


def _opt_bool(value: Any, key: str) -> bool | None:
    if value is None:
        return None
    return _as_bool(value, key)


def _as_int(value: Any, key: str, *, minimum: int = 1) -> int:
    try:
        out = int(value)
    except (TypeError, ValueError):
        raise SystemExit(f"{key}: expected integer, got {value!r}")
    if out < minimum:
        raise SystemExit(f"{key}: expected >= {minimum}, got {out}")
    return out


def load_settings(path: Path) -> Settings:
    repo_root = path.resolve().parent.parent
    env_path = repo_root / ".env"
    if env_path.is_file():
        load_dotenv(env_path)
    with path.open(encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}

    base = path.resolve().parent

    rec = Path(raw.get("recordings_dir", "../recordings")).expanduser()
    rec = (rec if rec.is_absolute() else base / rec).resolve()

    hls = Path(raw.get("hls_dir", "../data/hls")).expanduser()
    hls = (hls if hls.is_absolute() else base / hls).resolve()

    seg = int(raw.get("segment_seconds", 300))
    if seg < 30:
        raise SystemExit("segment_seconds must be at least 30.")

    transport = str(raw.get("rtsp_transport", "tcp"))
    if transport not in ("tcp", "udp", "udp_multicast", "http"):
        raise SystemExit(f"rtsp_transport: unsupported value {transport!r}.")

    rec_fmt = str(raw.get("recording_format", "mpegts")).lower()
    if rec_fmt not in ("mpegts", "mp4"):
        raise SystemExit("recording_format must be 'mpegts' or 'mp4'.")

    record_default = _as_bool(raw.get("record", True), "record")
    live_default = _as_bool(raw.get("live", True), "live")

    web_raw = raw.get("web") or {}
    web = WebSettings(
        host=str(web_raw.get("host", "0.0.0.0")),
        port=int(web_raw.get("port", 8765)),
    )
    multiscreen_raw = raw.get("multiscreen") or {}
    multiscreen_enabled = _as_bool(multiscreen_raw.get("enabled", False), "multiscreen.enabled")
    multiscreen_camera_ids_raw = multiscreen_raw.get("camera_ids") or []
    if not isinstance(multiscreen_camera_ids_raw, list):
        raise SystemExit("multiscreen.camera_ids: expected a list of camera IDs")
    multiscreen_camera_ids = [str(item) for item in multiscreen_camera_ids_raw]
    multiscreen_cols = _as_int(multiscreen_raw.get("cols", 2), "multiscreen.cols", minimum=1)
    multiscreen_tile_w = _as_int(
        multiscreen_raw.get("tile_width", 640),
        "multiscreen.tile_width",
        minimum=64,
    )
    multiscreen_tile_h = _as_int(
        multiscreen_raw.get("tile_height", 360),
        "multiscreen.tile_height",
        minimum=64,
    )
    multiscreen_fps = _as_int(multiscreen_raw.get("fps", 10), "multiscreen.fps", minimum=1)
    multiscreen_bitrate = str(multiscreen_raw.get("bitrate", "3000k"))
    multiscreen_preset = str(multiscreen_raw.get("preset", "veryfast"))
    multiscreen_output_id = str(multiscreen_raw.get("output_id", "multiscreen"))
    if not _SAFE_ID.match(multiscreen_output_id):
        raise SystemExit(
            "multiscreen.output_id is not safe for filesystem paths "
            "(allowed: letters, digits, '_' and '-'; must start alphanumeric)."
        )

    cams_raw = raw.get("cameras") or []
    cameras: list[Camera] = []
    seen_ids: set[str] = set()
    for i, c in enumerate(cams_raw):
        cid = str(c.get("id") or f"cam{i + 1}")
        if not _SAFE_ID.match(cid):
            raise SystemExit(
                f"camera id {cid!r} is not safe for filesystem paths "
                f"(allowed: letters, digits, '_' and '-'; must start alphanumeric)."
            )
        if cid in seen_ids:
            raise SystemExit(f"duplicate camera id {cid!r}.")
        seen_ids.add(cid)
        url_raw = str(c["url"])
        url = _expand_env_in_str(url_raw, context=f"camera {cid!r} url")
        cameras.append(
            Camera(
                id=cid,
                name=str(c.get("name") or cid),
                url=url,
                hevc_tag=bool(c.get("hevc_tag", False)),
                record=_opt_bool(c.get("record"), f"camera {cid!r} record"),
                live=_opt_bool(c.get("live"), f"camera {cid!r} live"),
                enabled=_as_bool(c.get("enabled", True), f"camera {cid!r} enabled"),
            )
        )
    if not cameras:
        raise SystemExit("No cameras defined in config.")
    known_ids = {cam.id for cam in cameras}
    missing = [cid for cid in multiscreen_camera_ids if cid not in known_ids]
    if missing:
        raise SystemExit(
            f"multiscreen.camera_ids contains unknown camera IDs: {', '.join(missing)}"
        )

    return Settings(
        recordings_dir=rec,
        hls_dir=hls,
        segment_seconds=seg,
        rtsp_transport=transport,
        recording_format=rec_fmt,
        cameras=cameras,
        web=web,
        record=record_default,
        live=live_default,
        multiscreen=MultiScreenSettings(
            enabled=multiscreen_enabled,
            camera_ids=multiscreen_camera_ids,
            cols=multiscreen_cols,
            tile_width=multiscreen_tile_w,
            tile_height=multiscreen_tile_h,
            fps=multiscreen_fps,
            bitrate=multiscreen_bitrate,
            preset=multiscreen_preset,
            output_id=multiscreen_output_id,
        ),
    )
