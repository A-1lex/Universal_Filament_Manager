"""Real subprocess checks for bounded, correlated calculation responses."""

import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from ufm.application.dto.worker_protocol import StatusMessage
from ufm.integrations.calculation_worker import (
    CalculationWorkerTransport,
    WorkerScope,
    WorkerTransportRejected,
)


class CalculationWorkerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ufm-worker-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.entry = self.root / "worker.py"
        self.scope = WorkerScope(uuid4(), "epoch-1", "request-1")
        self.response = {"v": 1, "kind": "status", "request_id": self.scope.request_id,
                         "printer_id": str(self.scope.printer_id), "source_epoch": self.scope.source_epoch,
                         "sequence": 1, "observed_at": "2026-10-27T08:00:00Z", "connection": "connected"}
        self.transport = CalculationWorkerTransport(Path(sys.executable).resolve(), self.entry, self.root, 2)

    def script(self, body: str) -> None:
        self.entry.write_text("import json,os,sys,time\nsys.stdin.buffer.read()\n" + body, "utf-8")

    async def test_real_child_returns_only_matching_scope(self) -> None:
        self.script(f"sys.stdout.write({json.dumps(json.dumps(self.response))})\n")
        message = await self.transport.exchange(b"{}", self.scope)
        self.assertIsInstance(message, StatusMessage)

    async def test_foreign_printer_epoch_or_request_is_rejected(self) -> None:
        for key, value in (("printer_id", str(uuid4())), ("source_epoch", "foreign"), ("request_id", "foreign")):
            with self.subTest(key=key):
                self.script(f"sys.stdout.write({json.dumps(json.dumps({**self.response, key: value}))})\n")
                with self.assertRaisesRegex(WorkerTransportRejected, "worker.scope_mismatch"):
                    await self.transport.exchange(b"{}", self.scope)

    async def test_large_stdout_and_stderr_are_stopped(self) -> None:
        for stream, size in (("stdout", 512 * 1024 + 1), ("stderr", 4097)):
            with self.subTest(stream=stream):
                self.script(f"sys.{stream}.write('x'*{size})\nsys.{stream}.flush()\ntime.sleep(20)\n")
                with self.assertRaisesRegex(WorkerTransportRejected, "worker.output_too_large"):
                    await self.transport.exchange(b"{}", self.scope)

    async def test_timeout_terminates_child(self) -> None:
        self.script("time.sleep(20)\n")
        transport = CalculationWorkerTransport(Path(sys.executable).resolve(), self.entry, self.root, 0.2)
        with self.assertRaisesRegex(WorkerTransportRejected, "worker.timed_out"):
            await transport.exchange(b"{}", self.scope)

    async def test_child_cannot_return_fake_commit_or_raw_exception(self) -> None:
        for body in ("sys.stdout.write('private-marker-invalid-json')\n",
                     "sys.stderr.write('private-marker-error')\nsys.exit(7)\n",
                     f"sys.stdout.write({json.dumps(json.dumps({**self.response, 'kind': 'finalization_outcome'}))})\n"):
            self.script(body)
            with self.assertRaises(WorkerTransportRejected) as caught:
                await self.transport.exchange(b"{}", self.scope)
            self.assertNotIn("private-marker", str(caught.exception))

    async def test_provider_secrets_not_forwarded_to_child(self) -> None:
        self.script(f"assert 'BAMBU_ACCESS_CODE' not in os.environ\n"
                    f"assert 'SPOOLMAN_TOKEN' not in os.environ\n"
                    f"sys.stdout.write({json.dumps(json.dumps(self.response))})\n")
        with patch.dict(os.environ, {"BAMBU_ACCESS_CODE": "private-marker", "SPOOLMAN_TOKEN": "secret"}):
            await self.transport.exchange(b"{}", self.scope)

    async def test_cancellation_cleans_up_child(self) -> None:
        self.script("time.sleep(20)\n")
        task = asyncio.create_task(self.transport.exchange(b"{}", self.scope))
        await asyncio.sleep(0.1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

    async def test_request_bound_before_child_start(self) -> None:
        with self.assertRaisesRegex(WorkerTransportRejected, "worker.request_invalid"):
            await self.transport.exchange(b"x" * (512 * 1024 + 1), self.scope)
