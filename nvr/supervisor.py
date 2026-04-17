from __future__ import annotations

import logging
import subprocess
import time
from collections.abc import Callable

log = logging.getLogger("nvr")


def supervise_ffmpeg(
    label: str,
    build_cmd: Callable[[], list[str]],
    stop: list[bool],
) -> None:
    """Run FFmpeg in a loop until stop; rebuild command each attempt (fresh paths/dirs)."""
    backoff = 1.0
    max_backoff = 60.0
    while not stop[0]:
        cmd = build_cmd()
        log.info("Starting FFmpeg: %s", label)
        try:
            proc = subprocess.Popen(cmd)
        except FileNotFoundError:
            log.error("ffmpeg not found; install ffmpeg and ensure it is on PATH")
            stop[0] = True
            return
        while proc.poll() is None and not stop[0]:
            time.sleep(0.5)
        if stop[0]:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            return
        code = proc.poll()
        log.warning(
            "FFmpeg exited (%s) with code %s; retrying in %.0fs",
            label,
            code,
            backoff,
        )
        t0 = time.monotonic()
        while time.monotonic() - t0 < backoff and not stop[0]:
            time.sleep(0.3)
        backoff = min(max_backoff, backoff * 2)
