"""The tracing setup itself (agent/tracing.py), started in a fresh Python process the way the agent starts it."""

import os
import subprocess
import sys
import threading
import warnings
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent.tracing import FailedRunsTurnRed

REPO = Path(__file__).resolve().parent.parent

START_AGENT_TRACING = """
import agent.tracing as tracing
with tracing.tracer_provider.get_tracer("test").start_as_current_span("hello"):
    pass
tracing.tracer_provider.force_flush()
print([type(p).__name__ for p in tracing.tracer_provider._active_span_processor._span_processors])
"""


@pytest.fixture(scope="module")
def started(tmp_path_factory):
    """Start tracing in a folder whose .env points it at a fake Phoenix collector; return what happened."""
    received = []

    class FakeCollector(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            received.append(self.path)
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    collector = HTTPServer(("127.0.0.1", 0), FakeCollector)
    threading.Thread(target=collector.serve_forever, daemon=True).start()
    folder = tmp_path_factory.mktemp("agent")
    (folder / ".env").write_text(f"PHOENIX_COLLECTOR_ENDPOINT=http://127.0.0.1:{collector.server_port}\n")
    env = {k: v for k, v in os.environ.items() if k != "PHOENIX_COLLECTOR_ENDPOINT"} | {"PYTHONPATH": str(REPO)}

    result = subprocess.run(
        [sys.executable, "-c", START_AGENT_TRACING],
        cwd=folder, env=env, capture_output=True, text=True, timeout=60, check=False,
    )
    collector.shutdown()
    assert result.returncode == 0, result.stderr
    return SimpleNamespace(processors=result.stdout.strip().splitlines()[-1], received=received)


def test_settings_from_dotenv_reach_the_tracing_setup(started):
    # .env is read before tracing is registered, so its collector endpoint is the one spans are sent to.
    assert "/v1/traces" in started.received


def test_failed_runs_turn_red_before_the_batched_export(started):
    # FailedRunsTurnRed must see each span first: once the exporter has it, changing its status is too late.
    assert started.processors == "['FailedRunsTurnRed', 'BatchSpanProcessor']"


def fake_failed_run(**fields):
    exception = SimpleNamespace(name="exception", attributes={"exception.message": "Rate limit exceeded"})
    return SimpleNamespace(attributes={"openinference.span.kind": "AGENT"}, events=[exception], **fields)


def test_failed_runs_turn_red_warns_once_if_the_span_internals_changed():
    turn_red = FailedRunsTurnRed()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        turn_red.on_end(fake_failed_run())  # a span without the private _status field it writes
        turn_red.on_end(fake_failed_run())

    [warning] = caught
    assert "FailedRunsTurnRed" in str(warning.message)
