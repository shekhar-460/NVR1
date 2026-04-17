from __future__ import annotations

from nvr.settings import Camera, Settings
from nvr.supervisor import supervise_ffmpeg


def build_hls_command(cam: Camera, settings: Settings) -> list[str]:
    cam_hls = settings.hls_dir / cam.id
    cam_hls.mkdir(parents=True, exist_ok=True)
    playlist = cam_hls / "stream.m3u8"
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
    if cam.hevc_tag:
        cmd.extend(["-c:v", "copy", "-tag:v", "hvc1"])
    else:
        cmd.extend(["-c", "copy"])
    cmd.extend(
        [
            "-f",
            "hls",
            "-hls_time",
            "2",
            "-hls_list_size",
            "8",
            "-hls_flags",
            "delete_segments+append_list+omit_endlist",
            "-hls_segment_filename",
            str(cam_hls / "segment_%03d.ts"),
            str(playlist),
        ]
    )
    return cmd


def run_camera_hls(cam: Camera, settings: Settings, stop: list[bool]) -> None:
    supervise_ffmpeg(
        f"hls:{cam.name} ({cam.id})",
        lambda: build_hls_command(cam, settings),
        stop,
    )


def ensure_hls_tree(settings: Settings) -> None:
    settings.hls_dir.mkdir(parents=True, exist_ok=True)
