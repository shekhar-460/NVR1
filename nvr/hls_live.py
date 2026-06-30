from __future__ import annotations

import threading

from nvr.ffmpeg_common import copy_codec_args, ffmpeg_input_args, hls_output_args
from nvr.settings import Camera, Settings
from nvr.supervisor import supervise_ffmpeg


def build_hls_command(cam: Camera, settings: Settings) -> list[str]:
    cam_hls = settings.hls_dir / cam.id
    cam_hls.mkdir(parents=True, exist_ok=True)
    playlist = cam_hls / "stream.m3u8"
    cmd = ffmpeg_input_args(cam, settings, normalize_timestamps=True)
    cmd.extend(copy_codec_args(cam))
    cmd.extend(
        hls_output_args(
            settings,
            str(cam_hls / "segment_%03d.ts"),
            playlist,
        )
    )
    return cmd


def run_camera_hls(cam: Camera, settings: Settings, stop: threading.Event) -> None:
    supervise_ffmpeg(
        f"hls:{cam.name} ({cam.id})",
        lambda: build_hls_command(cam, settings),
        stop,
        camera_id=cam.id,
        role="hls",
    )


def ensure_hls_tree(settings: Settings) -> None:
    settings.hls_dir.mkdir(parents=True, exist_ok=True)
