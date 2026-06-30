"""Shared FFmpeg command fragments used by the recorder and HLS pipelines."""

from __future__ import annotations

from pathlib import Path

from nvr.settings import Camera, Settings


def is_rtsp_url(url: str) -> bool:
    return url.lower().startswith("rtsp://") or url.lower().startswith("rtsps://")


def ffmpeg_base_args() -> list[str]:
    return ["ffmpeg", "-hide_banner", "-loglevel", "warning"]


def ffmpeg_input_block(
    cam: Camera,
    settings: Settings,
    *,
    normalize_timestamps: bool = False,
    thread_queue_size: int | None = None,
) -> list[str]:
    """Per-input flags for ``-i <url>`` (without the leading ``ffmpeg`` binary args).

    When ``normalize_timestamps`` is true, ignore source DTS and (for RTSP) use
    wall-clock timestamps so IP cameras with broken clocks do not flood muxers
    with non-monotonic DTS corrections.
    """
    fflags = "+genpts+discardcorrupt+nobuffer"
    if normalize_timestamps:
        fflags += "+igndts"
    args: list[str] = []
    if thread_queue_size is not None:
        args.extend(["-thread_queue_size", str(thread_queue_size)])
    args.extend(
        [
            "-fflags",
            fflags,
            "-flags",
            "low_delay",
            "-analyzeduration",
            "1000000",
            "-probesize",
            "1000000",
        ]
    )
    if is_rtsp_url(cam.url):
        args.extend(["-rtsp_transport", settings.rtsp_transport])
        if normalize_timestamps:
            args.extend(["-use_wallclock_as_timestamps", "1"])
    args.extend(["-i", cam.url])
    return args


def ffmpeg_input_args(cam: Camera, settings: Settings, *, normalize_timestamps: bool = False) -> list[str]:
    """Return the common ``ffmpeg ... -i URL -an`` preamble for one camera."""
    args = ffmpeg_base_args()
    args.extend(
        ffmpeg_input_block(cam, settings, normalize_timestamps=normalize_timestamps)
    )
    args.append("-an")
    return args


def mux_timestamp_args() -> list[str]:
    """Output-side timestamp normalization before any muxer (segment or HLS)."""
    return ["-avoid_negative_ts", "make_zero", "-max_muxing_queue_size", "1024"]


def hls_output_args(settings: Settings, segment_pattern: str, playlist: Path) -> list[str]:
    """Shared HLS muxer flags for per-camera and multiscreen pipelines."""
    return [
        *mux_timestamp_args(),
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
        segment_pattern,
        str(playlist),
    ]


def copy_codec_args(cam: Camera) -> list[str]:
    """Return the ``-c copy`` (and ``-tag:v hvc1`` when HEVC) args.

    The ``hvc1`` tag is needed for HEVC in MP4 and can help Safari identify the
    codec in HLS playlists; cameras with H.264 only omit ``hevc_tag`` in config.
    """
    if cam.hevc_tag:
        return ["-c:v", "copy", "-tag:v", "hvc1"]
    return ["-c", "copy"]
