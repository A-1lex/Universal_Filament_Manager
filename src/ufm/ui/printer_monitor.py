"""Qt thread host for an explicitly started, read-only printer event stream."""

from __future__ import annotations

import asyncio
import threading
from collections import deque
from collections.abc import AsyncIterator, Callable

from PySide6.QtCore import QObject, QThread, Signal

from ufm.application.dto.providers import (
    PrinterCapabilities,
    PrinterEvent,
    PrinterStatusSnapshot,
)
from ufm.application.ports.printers import PrinterProvider, ProviderError
from ufm.domain.enums import ProviderHealthState
from ufm.ui.windows_power import WindowsResumeDetector


async def _next_event(stream: AsyncIterator[PrinterEvent]) -> PrinterEvent:
    return await stream.__anext__()


class PrinterEventBufferOverflow(RuntimeError):
    """The monitor cannot preserve all observations until its consumer catches up."""


class PrinterMonitorTask(QThread):
    """Own one provider connection and reconnect transient failures safely."""

    event_available = Signal()
    status_available = Signal()
    capabilities_available = Signal()
    state_changed = Signal(str)
    failed = Signal(str)
    _health_check_interval_seconds = 15.0
    _event_buffer_limit = 256

    def __init__(
        self, provider_factory: Callable[[], PrinterProvider], parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._provider_factory = provider_factory
        self._resume_detector = WindowsResumeDetector()
        self._stop_requested = threading.Event()
        self._event_lock = threading.Lock()
        self._event_queue: deque[PrinterEvent] = deque()
        self._notification_pending = False
        self._latest_status: PrinterStatusSnapshot | None = None
        self._status_notification_pending = False
        self._latest_capabilities: PrinterCapabilities | None = None
        self._capabilities_notification_pending = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._monitor: asyncio.Task[None] | None = None

    def take_latest_event(self) -> PrinterEvent | None:
        """Drain observations for the visual-only latest-snapshot panel."""
        events = self.take_pending_events()
        return events[-1] if events else None

    def take_pending_events(self) -> tuple[PrinterEvent, ...]:
        """Drain every buffered event in receive order for durable consumers."""
        with self._event_lock:
            events = tuple(self._event_queue)
            self._event_queue.clear()
            self._notification_pending = False
            return events

    def take_latest_status(self) -> PrinterStatusSnapshot | None:
        with self._event_lock:
            status = self._latest_status
            self._latest_status = None
            self._status_notification_pending = False
            return status

    def take_latest_capabilities(self) -> PrinterCapabilities | None:
        with self._event_lock:
            capabilities = self._latest_capabilities
            self._latest_capabilities = None
            self._capabilities_notification_pending = False
            return capabilities

    def _publish(self, event: PrinterEvent) -> bool:
        should_notify = False
        with self._event_lock:
            if len(self._event_queue) >= self._event_buffer_limit:
                return False
            self._event_queue.append(event)
            if not self._notification_pending:
                self._notification_pending = True
                should_notify = True
        if should_notify:
            self.event_available.emit()
        return True

    def _publish_status(self, status: PrinterStatusSnapshot) -> None:
        should_notify = False
        with self._event_lock:
            self._latest_status = status
            if not self._status_notification_pending:
                self._status_notification_pending = True
                should_notify = True
        if should_notify:
            self.status_available.emit()

    def _publish_capabilities(self, capabilities: PrinterCapabilities) -> None:
        should_notify = False
        with self._event_lock:
            self._latest_capabilities = capabilities
            if not self._capabilities_notification_pending:
                self._capabilities_notification_pending = True
                should_notify = True
        if should_notify:
            self.capabilities_available.emit()

    def stop(self) -> None:
        self.requestInterruption()
        self._stop_requested.set()
        loop, monitor = self._loop, self._monitor
        if loop is not None and monitor is not None and loop.is_running():
            loop.call_soon_threadsafe(monitor.cancel)

    def run(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        monitor = loop.create_task(self._consume())
        self._monitor = monitor
        if self._stop_requested.is_set():
            monitor.cancel()
        try:
            loop.run_until_complete(monitor)
        except asyncio.CancelledError:
            pass
        finally:
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.run_until_complete(loop.shutdown_default_executor())
            asyncio.set_event_loop(None)
            loop.close()
            self._monitor = None
            self._loop = None

    async def _consume(self) -> None:
        retry_number = 0
        while not self.isInterruptionRequested():
            try:
                self.state_changed.emit("connecting" if retry_number == 0 else "retrying")
                await self._run_provider_once()
                if self.isInterruptionRequested():
                    return
                error: Exception = ProviderError("provider.stream_ended", retryable=True)
            except asyncio.CancelledError:
                raise
            except Exception as caught:
                error = caught
                if not isinstance(error, ProviderError) or not error.retryable:
                    self.state_changed.emit("offline")
                    self.failed.emit(type(error).__name__)
                    return
            if not isinstance(error, ProviderError) or not error.retryable:
                self.state_changed.emit("offline")
                self.failed.emit(type(error).__name__)
                return
            self.state_changed.emit("offline")
            delay = self._retry_delay(retry_number)
            retry_number += 1
            self.state_changed.emit("retrying")
            await asyncio.sleep(delay)

    async def _run_provider_once(self) -> None:
        provider = self._provider_factory()
        stream: AsyncIterator[PrinterEvent] | None = None
        next_event: asyncio.Task[PrinterEvent] | None = None
        try:
            await provider.connect()
            self.state_changed.emit("online")
            get_status = getattr(provider, "get_status", None)
            if callable(get_status):
                status = await get_status()
                if not isinstance(status, PrinterStatusSnapshot):
                    raise TypeError("printer.status_invalid")
                self._publish_status(status)
            get_capabilities = getattr(provider, "get_capabilities", None)
            if callable(get_capabilities):
                capabilities = await get_capabilities()
                if not isinstance(capabilities, PrinterCapabilities):
                    raise TypeError("printer.capabilities_invalid")
                self._publish_capabilities(capabilities)
            event_stream = provider.subscribe_events()
            stream = event_stream
            next_event = asyncio.create_task(_next_event(event_stream))
            health_method = getattr(provider, "health", None)
            next_health_check = (
                asyncio.get_running_loop().time() + self._health_check_interval_seconds
                if callable(health_method) else None
            )
            while not self.isInterruptionRequested():
                timeout = None
                if next_health_check is not None:
                    timeout = max(0.0, next_health_check - asyncio.get_running_loop().time())
                done, _ = await asyncio.wait({next_event}, timeout=timeout)
                if not done:
                    if not callable(health_method):
                        continue
                    if self._resume_detector.resumed():
                        self.state_changed.emit("stale")
                        raise ProviderError("provider.resumed_after_sleep", retryable=True)
                    health = await health_method()
                    next_health_check = (
                        asyncio.get_running_loop().time() + self._health_check_interval_seconds
                    )
                    if health.state is ProviderHealthState.HEALTHY:
                        self.state_changed.emit("online")
                        if callable(get_status):
                            status = await get_status()
                            if not isinstance(status, PrinterStatusSnapshot):
                                raise TypeError("printer.status_invalid")
                            self._publish_status(status)
                        continue
                    if health.state is ProviderHealthState.DEGRADED:
                        self.state_changed.emit("stale")
                        raise ProviderError(
                            health.reason_code, retryable=health.retryable,
                        )
                    if health.state is ProviderHealthState.UNAVAILABLE:
                        self.state_changed.emit("offline")
                        raise ProviderError(
                            health.reason_code, retryable=health.retryable,
                        )
                    continue
                try:
                    event = next_event.result()
                except StopAsyncIteration:
                    if not self.isInterruptionRequested():
                        raise ProviderError(
                            "provider.stream_ended", retryable=True,
                        ) from None
                    return
                if not isinstance(event, PrinterEvent):
                    raise TypeError("printer.event_invalid")
                if not self._publish(event):
                    raise PrinterEventBufferOverflow("printer.event_buffer_overflow")
                next_event = asyncio.create_task(_next_event(event_stream))
        finally:
            try:
                if next_event is not None and not next_event.done():
                    next_event.cancel()
                    await asyncio.gather(next_event, return_exceptions=True)
                if stream is not None:
                    close_stream = getattr(stream, "aclose", None)
                    if callable(close_stream):
                        await close_stream()
            finally:
                # A stream cleanup error must never skip releasing the provider.
                await provider.disconnect()

    @staticmethod
    def _retry_delay(retry_number: int) -> float:
        """Capped exponential backoff: 1, 2, 4… up to 30 seconds."""
        return min(30.0, float(2 ** min(retry_number, 5)))
