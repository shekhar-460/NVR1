from __future__ import annotations

import logging
import os
import signal
import subprocess
import threading
import time
from collections.abc import Callable

from nvr.state import REGISTRY, Role

log = logging.getLogger("nvr")

# A run that survives at least this long is considered "healthy" — the backoff
# resets and the failure streak clears, so one flaky network blip later won't
# push retries out to the 60-second cap.
_HEALTHY_RUNTIME_S = 30.0

# If FFmpeg exits in under this many seconds, count it as an "immediate" failure.
_IMMEDIATE_FAIL_S = 3.0

# After this many consecutive immediate failures, give up on the camera (most
# likely: wrong URL, wrong credentials, unsupported codec). The registry marks
# it failed so the UI / health endpoint can show it.
_MAX_IMMEDIATE_FAILURES = 10


def _pump_stderr(proc: subprocess.Popen[bytes], logger: logging.Logger, last_line: list[str]) -> None:
    """Read FFmpeg stderr line-by-line into the per-camera logger."""
    stream = proc.stderr
    if stream is None:
        return
    try:
        for raw in iter(stream.readline, b""):
            line = raw.decode("utf-8", errors="replace").rstrip()
            if not line:
                continue
            last_line[0] = line
            lowered = line.lower()
            if "error" in lowered or "failed" in lowered:
                logger.error(line)
            elif "warning" in lowered:
                logger.warning(line)
            else:
                logger.info(line)
    except Exception:  # pragma: no cover - defensive
        logger.debug("stderr pump stopped", exc_info=True)
    finally:
        try:
            stream.close()
        except Exception:
            pass


def _terminate(proc: subprocess.Popen[bytes]) -> None:
    """Terminate an FFmpeg process (and any children) without hanging."""
    if proc.poll() is not None:
        return
    try:
        pgid = os.getpgid(proc.pid)
        os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.terminate()
        except Exception:
            pass
    try:
        proc.wait(timeout=5)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        pgid = os.getpgid(proc.pid)
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except Exception:
            pass
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass


def supervise_ffmpeg(
    label: str,
    build_cmd: Callable[[], list[str]],
    stop: threading.Event,
    *,
    camera_id: str,
    role: Role,
    restart_when: Callable[[float], str | None] | None = None,
) -> None:
    """Run FFmpeg in a loop until ``stop`` is set; rebuild the command each attempt.

    Each camera pipeline is independent: failures here never signal the global
    ``stop`` event, and this loop keeps retrying so other cameras are unaffected.
    """
    backoff = 1.0
    max_backoff = 60.0
    cam_logger = logging.getLogger(f"nvr.ffmpeg.{role}.{camera_id}")
    chronic_failure_logged = False

    while not stop.is_set():
        try:
            cmd = build_cmd()
        except Exception:
            cam_logger.exception("Failed to build FFmpeg command for %s", label)
            REGISTRY.mark_failed_permanently(camera_id, role)
            if stop.wait(min(backoff, max_backoff)):
                return
            backoff = min(max_backoff, backoff * 2)
            continue

        log.info("Starting FFmpeg: %s", label)
        cam_logger.debug("cmd: %s", " ".join(cmd))
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
        except FileNotFoundError:
            log.error(
                "ffmpeg not found for %s; install ffmpeg and ensure it is on PATH "
                "(other cameras keep running)",
                label,
            )
            REGISTRY.mark_failed_permanently(camera_id, role)
            if stop.wait(max_backoff):
                return
            continue
        except OSError as exc:
            cam_logger.error("Failed to start FFmpeg for %s: %s", label, exc)
            REGISTRY.mark_failed_permanently(camera_id, role)
            if stop.wait(min(backoff, max_backoff)):
                return
            backoff = min(max_backoff, backoff * 2)
            continue

        REGISTRY.mark_started(camera_id, role)
        chronic_failure_logged = False
        started = time.monotonic()
        last_line: list[str] = [""]
        pump = threading.Thread(
            target=_pump_stderr,
            args=(proc, cam_logger, last_line),
            name=f"ffmpeg-stderr-{role}-{camera_id}",
            daemon=True,
        )
        pump.start()

        while proc.poll() is None and not stop.is_set():
            stop.wait(0.5)
            if restart_when is not None:
                runtime_s = time.monotonic() - started
                reason = restart_when(runtime_s)
                if reason:
                    cam_logger.warning("Restarting FFmpeg (%s): %s", label, reason)
                    _terminate(proc)
                    break

        if stop.is_set():
            _terminate(proc)
            pump.join(timeout=2)
            REGISTRY.mark_exited(
                camera_id,
                role,
                code=proc.returncode,
                error=None,
                was_healthy=True,
            )
            return

        code = proc.poll()
        pump.join(timeout=2)
        runtime = time.monotonic() - started
        was_healthy = runtime >= _HEALTHY_RUNTIME_S
        REGISTRY.mark_exited(
            camera_id,
            role,
            code=code,
            error=last_line[0] or None,
            was_healthy=was_healthy,
        )
        status = REGISTRY.status_for(camera_id, role)

        if was_healthy:
            backoff = 1.0
            log.warning(
                "FFmpeg exited (%s) after %.0fs with code %s; retrying in %.0fs",
                label,
                runtime,
                code,
                backoff,
            )
        elif runtime < _IMMEDIATE_FAIL_S:
            if status.failure_streak >= _MAX_IMMEDIATE_FAILURES:
                REGISTRY.mark_failed_permanently(camera_id, role)
                backoff = max_backoff
                if not chronic_failure_logged:
                    log.error(
                        "FFmpeg for %s failed %d times in a row with no healthy run; "
                        "retrying every %.0fs (other cameras unaffected). Last stderr: %s",
                        label,
                        status.failure_streak,
                        backoff,
                        last_line[0] or "(empty)",
                    )
                    chronic_failure_logged = True
            else:
                log.warning(
                    "FFmpeg exited (%s) after %.1fs with code %s (streak=%d); retrying in %.0fs",
                    label,
                    runtime,
                    code,
                    status.failure_streak,
                    backoff,
                )
        else:
            log.warning(
                "FFmpeg exited (%s) after %.0fs with code %s; retrying in %.0fs",
                label,
                runtime,
                code,
                backoff,
            )

        if stop.wait(backoff):
            return
        backoff = min(max_backoff, backoff * 2)
