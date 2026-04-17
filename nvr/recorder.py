from __future__ import annotations

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
    # Single directory per camera (no nested date folders): FFmpeg does not mkdir %Y-%m-%d for segment.
    pattern = str(out_dir / f"%Y-%m-%d_%H-%M-%S{ext}")
    cmd: list[str] = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-rtsp_transport",
        settings.rtsp_transport,
        "-fflags",
        "+genpts",
        "-i",
        cam.url,
        "-an",
    ]
    if cam.hevc_tag and fmt == "mp4":
        cmd.extend(["-c:v", "copy", "-tag:v", "hvc1"])
    else:
        cmd.extend(["-c", "copy"])
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


def run_camera_recorder(cam: Camera, settings: Settings, stop: list[bool]) -> None:
    supervise_ffmpeg(
        f"record:{cam.name} ({cam.id})",
        lambda: build_record_command(cam, settings),
        stop,
    )


def ensure_recording_tree(settings: Settings) -> None:
    settings.recordings_dir.mkdir(parents=True, exist_ok=True)
