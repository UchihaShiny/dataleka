"""Cancellation and chart-result validation; no CLI, credentials or external requests."""

import os

os.environ["PYTHON_DOTENV_DISABLED"] = "1"
import asyncio
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from webapp.api import claude_chat, chat_stream, reports


class LifecycleTests(unittest.TestCase):
    def test_disconnecting_response_signals_worker(self):
        stopped = threading.Event()

        def produce(cancel):
            try:
                yield {"t": "text", "s": "test"}
                cancel.wait(2)
            finally:
                stopped.set()

        async def run():
            request = SimpleNamespace(
                is_disconnected=lambda: asyncio.sleep(0, result=False)
            )
            stream = chat_stream.response_events(request, produce)
            self.assertIn("text", await anext(stream))
            await stream.aclose()
            self.assertTrue(await asyncio.to_thread(stopped.wait, 1))

        asyncio.run(run())

    def test_cli_cancellation_kills_blocked_process_and_releases_lock(self):
        class Process:
            def __init__(self, *args, **kwargs):
                self.killed = threading.Event()
                Process.last = self
                self.stdin = SimpleNamespace(write=lambda s: None, close=lambda: None)
                self.stderr = SimpleNamespace(read=lambda: "")
                self.stdout = self.lines()

            def lines(self):
                yield json.dumps(
                    {
                        "type": "system",
                        "subtype": "init",
                        "tools": [],
                        "session_id": "test",
                    }
                )
                self.killed.wait(2)

            def poll(self):
                return 0 if self.killed.is_set() else None

            def kill(self):
                self.killed.set()

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(claude_chat, "WORKDIR", Path(tmp)),
            patch.object(claude_chat, "claude_exe", return_value="fake"),
            patch.object(claude_chat.subprocess, "Popen", Process),
        ):
            cancel = threading.Event()
            answer = claude_chat.ask("Demo", "project", cancel=cancel)
            self.assertEqual(next(answer)["t"], "session")
            cancel.set()
            self.assertTrue(Process.last.killed.wait(1))
            list(answer)
            self.assertTrue(claude_chat._busy.acquire(blocking=False))
            claude_chat._busy.release()

    def test_close_generator_kills_process(self):
        killed = []
        proc = SimpleNamespace(
            stdin=SimpleNamespace(write=lambda s: None, close=lambda: None),
            stdout=iter(
                [json.dumps({"type": "system", "subtype": "init", "tools": []})]
            ),
            stderr=SimpleNamespace(read=lambda: ""),
            poll=lambda: None,
            kill=lambda: killed.append(True),
        )
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(claude_chat, "WORKDIR", Path(tmp)),
            patch.object(claude_chat, "claude_exe", return_value="fake"),
            patch.object(claude_chat.subprocess, "Popen", return_value=proc),
        ):
            answer = claude_chat.ask("Demo", "project")
            next(answer)
            answer.close()
            self.assertTrue(killed)

    def test_unexpected_cli_exit_does_not_read_unbounded_stderr(self):
        proc = SimpleNamespace(
            stdin=SimpleNamespace(write=lambda s: None, close=lambda: None),
            stdout=iter([]),
            poll=lambda: 0,
            kill=lambda: None,
        )
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(claude_chat, "WORKDIR", Path(tmp)),
            patch.object(claude_chat, "claude_exe", return_value="fake"),
            patch.object(claude_chat.subprocess, "Popen", return_value=proc) as spawn,
        ):
            result = list(claude_chat.ask("Demo", "project"))
            self.assertEqual(result[-1]["t"], "error")
            self.assertIn("Kiểm tra đăng nhập", result[-1]["msg"])
            self.assertEqual(
                spawn.call_args.kwargs["stderr"], claude_chat.subprocess.DEVNULL
            )

    def test_chart_values_are_numeric_or_unknown(self):
        spec = reports.check_spec(
            {
                "title": "Test",
                "sql": "select 1",
                "chart": "line",
                "x": "date",
                "y": ["rev"],
            }
        )
        for value in ["12", False, {"value": 3}, float("inf")]:
            with self.assertRaises(reports.ReportError):
                reports.validate_chart_data(
                    spec, ["date", "rev"], [{"date": "2026-11-15", "rev": value}]
                )
        reports.validate_chart_data(
            spec,
            ["date", "rev"],
            [{"date": "2026-11-15", "rev": None}, {"date": "2026-11-16", "rev": -10}],
        )
        with self.assertRaises(reports.ReportError):
            reports.validate_chart_data(spec, ["date"], [])
        reports.validate_chart_data(
            {"chart": "table"}, ["text"], [{"text": "Keep text"}]
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
