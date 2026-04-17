from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

_ENV_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass
class Camera:
    id: str
    name: str
    url: str
    # H.265/HEVC in MP4 or HLS often needs -tag:v hvc1 (omit for H.264-only cameras).
    hevc_tag: bool = False


@dataclass
class WebSettings:
    host: str
    port: int


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


def load_settings(path: Path) -> Settings:
    repo_root = path.resolve().parent.parent
    env_path = repo_root / ".env"
    if env_path.is_file():
        load_dotenv(env_path)
    with path.open(encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}
    base = path.resolve().parent
    rec = Path(raw.get("recordings_dir", "../recordings")).expanduser()
    if not rec.is_absolute():
        rec = (base / rec).resolve()
    else:
        rec = rec.resolve()
    hls = Path(raw.get("hls_dir", "../data/hls")).expanduser()
    if not hls.is_absolute():
        hls = (base / hls).resolve()
    else:
        hls = hls.resolve()
    seg = int(raw.get("segment_seconds", 300))
    transport = str(raw.get("rtsp_transport", "tcp"))
    rec_fmt = str(raw.get("recording_format", "mpegts")).lower()
    if rec_fmt not in ("mpegts", "mp4"):
        raise SystemExit("recording_format must be 'mpegts' or 'mp4'.")
    web_raw = raw.get("web") or {}
    web = WebSettings(
        host=str(web_raw.get("host", "0.0.0.0")),
        port=int(web_raw.get("port", 8765)),
    )
    cams_raw = raw.get("cameras") or []
    cameras: list[Camera] = []
    for i, c in enumerate(cams_raw):
        cid = str(c.get("id") or f"cam{i + 1}")
        url_raw = str(c["url"])
        url = _expand_env_in_str(url_raw, context=f"camera {cid!r} url")
        cameras.append(
            Camera(
                id=cid,
                name=str(c.get("name") or cid),
                url=url,
                hevc_tag=bool(c.get("hevc_tag", False)),
            )
        )
    if not cameras:
        raise SystemExit("No cameras defined in config.")
    return Settings(
        recordings_dir=rec,
        hls_dir=hls,
        segment_seconds=max(30, seg),
        rtsp_transport=transport,
        recording_format=rec_fmt,
        cameras=cameras,
        web=web,
    )
