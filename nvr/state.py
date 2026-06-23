"""In-memory registry of per-camera pipeline state.

Each (camera_id, role) pair — role is ``"record"`` or ``"hls"`` — has its own
``PipelineStatus`` that the supervisor writes to and the web API reads from.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Literal

Role = Literal["record", "hls"]


@dataclass
class PipelineStatus:
    camera_id: str
    role: Role
    running: bool = False
    started_at: float | None = None
    last_exit_code: int | None = None
    last_exit_at: float | None = None
    last_error: str | None = None
    restart_count: int = 0
    failure_streak: int = 0
    # Set by the supervisor when repeated immediate failures (e.g. bad URL or
    # wrong credentials) make further retries pointless.
    failed_permanently: bool = False

    def as_dict(self) -> dict[str, object]:
        now = time.time()
        uptime = (now - self.started_at) if (self.running and self.started_at) else None
        return {
            "camera_id": self.camera_id,
            "role": self.role,
            "running": self.running,
            "uptime_s": uptime,
            "restart_count": self.restart_count,
            "failure_streak": self.failure_streak,
            "failed_permanently": self.failed_permanently,
            "last_exit_code": self.last_exit_code,
            "last_exit_at": self.last_exit_at,
            "last_error": self.last_error,
        }


@dataclass
class Registry:
    """Thread-safe container for all pipeline statuses."""

    _lock: threading.Lock = field(default_factory=threading.Lock)
    _items: dict[tuple[str, Role], PipelineStatus] = field(default_factory=dict)

    def status_for(self, camera_id: str, role: Role) -> PipelineStatus:
        key = (camera_id, role)
        with self._lock:
            status = self._items.get(key)
            if status is None:
                status = PipelineStatus(camera_id=camera_id, role=role)
                self._items[key] = status
            return status

    def snapshot(self) -> list[dict[str, object]]:
        with self._lock:
            return [s.as_dict() for s in self._items.values()]

    def mark_started(self, camera_id: str, role: Role) -> None:
        s = self.status_for(camera_id, role)
        with self._lock:
            s.running = True
            s.started_at = time.time()
            s.failed_permanently = False

    def mark_exited(
        self,
        camera_id: str,
        role: Role,
        *,
        code: int | None,
        error: str | None,
        was_healthy: bool,
    ) -> None:
        s = self.status_for(camera_id, role)
        with self._lock:
            s.running = False
            s.last_exit_code = code
            s.last_exit_at = time.time()
            s.last_error = error
            s.restart_count += 1
            if was_healthy:
                s.failure_streak = 0
            else:
                s.failure_streak += 1

    def mark_failed_permanently(self, camera_id: str, role: Role) -> None:
        s = self.status_for(camera_id, role)
        with self._lock:
            s.failed_permanently = True
            s.running = False


REGISTRY = Registry()
