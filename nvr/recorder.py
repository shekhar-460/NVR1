from __future__ import annotations

import threading

from nvr.ffmpeg_common import copy_codec_args, ffmpeg_input_args, mux_timestamp_args
from nvr.settings import Camera, Settings
from nvr.supervisor import supervise_ffmpeg


def build_record_command(cam: Camera, settings: Settings) -> list[str]:
    out_dir = settings.recordings_dir / cam.id
    out_dir.mkdir(parents=True, exist_ok=True)
    fmt = settings.recording_format
    if fmt == "mp4":
        ext = ".mp4"
        seg_fmt = "mp4"
    else:
        ext = ".ts"
        seg_fmt = "mpegts"
    # Single directory per camera (no nested date folders): FFmpeg does not mkdir
    # %Y-%m-%d for segment output.
    pattern = str(out_dir / f"%Y-%m-%d_%H-%M-%S{ext}")
    cmd = ffmpeg_input_args(cam, settings, normalize_timestamps=True)
    cmd.extend(copy_codec_args(cam))
    cmd.extend(mux_timestamp_args())
    cmd.extend(
        [
            "-f",
            "segment",
            "-segment_time",
            str(settings.segment_seconds),
            "-segment_format",
            seg_fmt,
            "-strftime",
            "1",
            "-reset_timestamps",
            "1",
            "-break_non_keyframes",
            "1",
            pattern,
        ]
    )
    return cmd


def run_camera_recorder(cam: Camera, settings: Settings, stop: threading.Event) -> None:
    supervise_ffmpeg(
        f"record:{cam.name} ({cam.id})",
        lambda: build_record_command(cam, settings),
        stop,
        camera_id=cam.id,
        role="record",
    )


def ensure_recording_tree(settings: Settings) -> None:
    settings.recordings_dir.mkdir(parents=True, exist_ok=True)
