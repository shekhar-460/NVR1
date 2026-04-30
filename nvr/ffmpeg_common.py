"""Shared FFmpeg command fragments used by the recorder and HLS pipelines."""

from __future__ import annotations

from nvr.settings import Camera, Settings


def ffmpeg_input_args(cam: Camera, settings: Settings) -> list[str]:
    """Return the common ``ffmpeg ... -i URL -an`` preamble for one camera."""
    return [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
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
        "-an",
    ]


def copy_codec_args(cam: Camera) -> list[str]:
    """Return the ``-c copy`` (and ``-tag:v hvc1`` when HEVC) args.

    The ``hvc1`` tag is needed for HEVC in MP4 and can help Safari identify the
    codec in HLS playlists; cameras with H.264 only omit ``hevc_tag`` in config.
    """
    if cam.hevc_tag:
        return ["-c:v", "copy", "-tag:v", "hvc1"]
    return ["-c", "copy"]
