"""Bounded one-shot process transport; a worker can return facts, never commit.

The application supplies trusted, bundled executable/entrypoint paths and an
isolated working directory. This is not an OS sandbox or a live job worker.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from ufm.application.dto.worker_protocol import (
    MAX_WIRE_BYTES,
    WorkerMessage,
    WorkerProtocolRejected,
    decode_worker_message,
)
from ufm.application.dto.worker_protocol import WorkerScope as WorkerScope


class WorkerTransportRejected(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)


def packaged_calculation_worker(workdir: Path) -> CalculationWorkerTransport:
    """Resolve the local worker bundle for frozen Studio or a source checkout.

    This creates no process and does not enable a calculator or accounting
    policy. Callers still need explicit receipt/evidence and authority gates.
    """
    if getattr(sys, "frozen", False):
        bundle_root_value = vars(sys).get("_MEIPASS")
        if not isinstance(bundle_root_value, str):
            raise WorkerTransportRejected("worker.bundle_unavailable")
        bundle_root = Path(bundle_root_value)
        executable = bundle_root / "runtime" / "node.exe"
        entrypoint = bundle_root / "ufm" / "integrations" / "haspel_worker.mjs"
    else:
        package_dir = Path(__file__).resolve().parent
        executable_name = shutil.which("node")
        if executable_name is None:
            raise WorkerTransportRejected("worker.bundle_unavailable")
        executable = Path(executable_name).resolve()
        entrypoint = package_dir / "haspel_worker.mjs"
    resolved_workdir = workdir.resolve()
    if not executable.is_file() or not entrypoint.is_file() or not resolved_workdir.is_absolute():
        raise WorkerTransportRejected("worker.bundle_unavailable")
    return CalculationWorkerTransport(executable, entrypoint, resolved_workdir)


async def _read_bounded(reader: asyncio.StreamReader, limit: int) -> bytes:
    result = bytearray()
    while chunk := await reader.read(min(65536, limit + 1 - len(result))):
        result.extend(chunk)
        if len(result) > limit:
            raise WorkerTransportRejected("worker.output_too_large")
    return bytes(result)


@dataclass(frozen=True, slots=True)
class CalculationWorkerTransport:
    executable: Path
    entrypoint: Path
    workdir: Path
    timeout_seconds: float = 5.0

    async def exchange(self, request: bytes, expected: WorkerScope) -> WorkerMessage:
        if type(request) is not bytes or not request or len(request) > MAX_WIRE_BYTES:
            raise WorkerTransportRejected("worker.request_invalid")
        if not 0 < self.timeout_seconds <= 60:
            raise WorkerTransportRejected("worker.timeout_invalid")
        if not self.executable.is_absolute() or not self.entrypoint.is_absolute() or not self.workdir.is_absolute():
            raise WorkerTransportRejected("worker.paths_invalid")
        # Do not forward provider tokens, API keys or .env-backed configuration.
        environment = {key: value for key, value in os.environ.items()
                       if key.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH"}}
        environment.update({"NODE_TEST_CONTEXT": "ufm-calculation-worker",
                            "DATA_DIR": str(self.workdir / "data"),
                            "LOG_DIR": str(self.workdir / "logs")})
        process: asyncio.subprocess.Process | None = None
        try:
            no_window = int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if os.name == "nt" else 0
            process = await asyncio.create_subprocess_exec(
                str(self.executable), str(self.entrypoint), cwd=self.workdir, env=environment,
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE, limit=MAX_WIRE_BYTES + 1,
                creationflags=no_window,
            )
            assert process.stdin is not None and process.stdout is not None and process.stderr is not None

            async def feed() -> None:
                assert process is not None and process.stdin is not None
                process.stdin.write(request)
                try:
                    await process.stdin.drain()
                finally:
                    process.stdin.close()

            stdout, _, exit_code, _ = await asyncio.wait_for(
                asyncio.gather(_read_bounded(process.stdout, MAX_WIRE_BYTES),
                               _read_bounded(process.stderr, 4096), process.wait(), feed()),
                timeout=self.timeout_seconds,
            )
            if exit_code != 0:
                raise WorkerTransportRejected("worker.process_failed")
            try:
                message = decode_worker_message(stdout)
            except WorkerProtocolRejected:
                raise WorkerTransportRejected("worker.response_invalid") from None
            if (message.printer_id != expected.printer_id or message.source_epoch != expected.source_epoch
                    or message.request_id != expected.request_id):
                raise WorkerTransportRejected("worker.scope_mismatch")
            return message
        except TimeoutError:
            raise WorkerTransportRejected("worker.timed_out") from None
        except OSError:
            raise WorkerTransportRejected("worker.process_unavailable") from None
        finally:
            if process is not None and process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await process.wait()
