from __future__ import annotations

import math
import threading

from nvr.settings import Camera, Settings
from nvr.supervisor import supervise_ffmpeg


def selected_multiscreen_cameras(settings: Settings) -> list[Camera]:
    selected_ids = settings.multiscreen.camera_ids
    live_cameras = [cam for cam in settings.cameras if settings.should_live(cam)]
    if selected_ids:
        live_by_id = {cam.id: cam for cam in live_cameras}
        return [live_by_id[cid] for cid in selected_ids if cid in live_by_id]
    return live_cameras


def build_multiscreen_hls_command(settings: Settings) -> list[str]:
    ms = settings.multiscreen
    cameras = selected_multiscreen_cameras(settings)
    if not cameras:
        raise RuntimeError("No live cameras available for multiscreen output.")

    cols = max(1, ms.cols)
    rows = math.ceil(len(cameras) / cols)
    tile_w = ms.tile_width
    tile_h = ms.tile_height
    canvas_w = cols * tile_w
    canvas_h = rows * tile_h

    out_dir = settings.hls_dir / ms.output_id
    out_dir.mkdir(parents=True, exist_ok=True)
    playlist = out_dir / "stream.m3u8"

    cmd: list[str] = ["ffmpeg", "-hide_banner", "-loglevel", "warning"]
    for cam in cameras:
        cmd.extend(
            [
                "-fflags",
                "+genpts+discardcorrupt+nobuffer",
                "-flags",
                "low_delay",
                "-analyzeduration",
                "1000000",
                "-probesize",
                "1000000",
                "-rw_timeout",
                "10000000",
                "-rtsp_transport",
                settings.rtsp_transport,
                "-i",
                cam.url,
            ]
        )

    # Normalize all inputs to fixed-size tiles and compose into one canvas.
    filter_parts: list[str] = []
    layout_parts: list[str] = []
    for idx, _cam in enumerate(cameras):
        filter_parts.append(
            f"[{idx}:v]fps={ms.fps},scale={tile_w}:{tile_h}:force_original_aspect_ratio=decrease,"
            f"pad={tile_w}:{tile_h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1[v{idx}]"
        )
        x = (idx % cols) * tile_w
        y = (idx // cols) * tile_h
        layout_parts.append(f"{x}_{y}")
    filter_parts.append(
        "".join(f"[v{idx}]" for idx in range(len(cameras)))
        + f"xstack=inputs={len(cameras)}:layout="
        + "|".join(layout_parts)
        + f":fill=black,crop={canvas_w}:{canvas_h}[vout]"
    )

    bufsize = ms.bitrate
    if ms.bitrate.endswith("k"):
        try:
            bufsize = f"{int(ms.bitrate[:-1]) * 2}k"
        except ValueError:
            bufsize = ms.bitrate

    cmd.extend(
        [
            "-filter_complex",
            ";".join(filter_parts),
            "-map",
            "[vout]",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            ms.preset,
            "-tune",
            "zerolatency",
            "-pix_fmt",
            "yuv420p",
            "-g",
            str(ms.fps * 2),
            "-sc_threshold",
            "0",
            "-b:v",
            ms.bitrate,
            "-maxrate",
            ms.bitrate,
            "-bufsize",
            bufsize,
            "-f",
            "hls",
            "-hls_time",
            str(settings.live_hls.segment_seconds),
            "-hls_list_size",
            str(settings.live_hls.list_size),
            "-hls_flags",
            "delete_segments+append_list+omit_endlist+independent_segments",
            "-hls_start_number_source",
            "epoch",
            "-hls_delete_threshold",
            str(settings.live_hls.delete_threshold),
            "-hls_segment_filename",
            str(out_dir / "segment_%03d.ts"),
            str(playlist),
        ]
    )
    return cmd


def run_multiscreen_hls(settings: Settings, stop: threading.Event) -> None:
    ms = settings.multiscreen
    supervise_ffmpeg(
        f"hls:Multiscreen ({ms.output_id})",
        lambda: build_multiscreen_hls_command(settings),
        stop,
        camera_id=ms.output_id,
        role="hls",
    )
