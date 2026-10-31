"""Small Windows suspend/resume detector for live printer sessions."""

from __future__ import annotations

import ctypes
import os
from collections.abc import Callable


def _windows_clock_snapshot() -> tuple[float, float] | None:
    """Return (wall uptime, awake uptime) seconds; wall uptime includes sleep."""
    if os.name != "nt":
        return None
    try:
        # WinDLL exists only on Windows; resolve it dynamically so the module
        # remains type-checkable on the other CI platforms.
        win_dll = getattr(ctypes, "WinDLL", None)
        if win_dll is None:
            return None
        kernel32 = win_dll("kernel32", use_last_error=True)
        get_tick_count = kernel32.GetTickCount64
        get_tick_count.restype = ctypes.c_ulonglong
        query_unbiased = kernel32.QueryUnbiasedInterruptTime
        query_unbiased.argtypes = [ctypes.POINTER(ctypes.c_ulonglong)]
        query_unbiased.restype = ctypes.c_int
        awake_100ns = ctypes.c_ulonglong()
        if not query_unbiased(ctypes.byref(awake_100ns)):
            return None
        wall_seconds = float(get_tick_count()) / 1000.0
        awake_seconds = float(awake_100ns.value) / 10_000_000.0
        return wall_seconds, awake_seconds
    except (AttributeError, OSError, TypeError, ValueError):
        return None


class WindowsResumeDetector:
    """Detect a sleep gap without treating normal idle time as suspension."""

    def __init__(
        self,
        snapshot: Callable[[], tuple[float, float] | None] = _windows_clock_snapshot,
        *,
        threshold_seconds: float = 2.0,
    ) -> None:
        if threshold_seconds <= 0:
            raise ValueError("power.resume_threshold_invalid")
        self._snapshot = snapshot
        self._threshold_seconds = threshold_seconds
        self._previous_sleep_total: float | None = None

    def resumed(self) -> bool:
        clocks = self._snapshot()
        if clocks is None:
            return False
        wall_seconds, awake_seconds = clocks
        sleep_total = wall_seconds - awake_seconds
        previous = self._previous_sleep_total
        self._previous_sleep_total = sleep_total
        return previous is not None and sleep_total - previous >= self._threshold_seconds
