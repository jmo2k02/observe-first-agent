"""Seam A setup: the real helpdesk service over HTTP, a scripted fake model and an in-memory span exporter.

No network access and no API key needed.
"""

import os
import socket
import threading
import time

import httpx
import pytest
import uvicorn
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from smolagents import ChatMessage, MessageRole, Model
from smolagents.models import ChatMessageToolCall, ChatMessageToolCallFunction
from smolagents.monitoring import TokenUsage

from service.main import app


@pytest.fixture(scope="session")
def helpdesk_url():
    """Run the real FastAPI service on a free local port for the whole test session."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            if httpx.get(f"{url}/health").status_code == 200:
                break
        except httpx.TransportError:
            time.sleep(0.1)
    else:
        pytest.fail("helpdesk service did not start")
    os.environ["HELPDESK_URL"] = url
    yield url
    server.should_exit = True


@pytest.fixture(scope="session")
def exporter():
    """The agent's real tracing setup (agent/tracing.py), with spans kept in memory instead of sent to Phoenix.

    Spans are batched in the background as in production, so reading them first waits for the batch.
    """
    from agent.tracing import tracer_provider

    class BatchedInMemoryExporter(InMemorySpanExporter):
        def get_finished_spans(self):
            tracer_provider.force_flush()
            return super().get_finished_spans()

        def clear(self):
            tracer_provider.force_flush()
            super().clear()

    exporter = BatchedInMemoryExporter()
    tracer_provider.add_span_processor(BatchSpanProcessor(exporter))  # replaces the Phoenix exporter
    return exporter


@pytest.fixture
def spans(helpdesk_url, exporter):
    exporter.clear()
    return exporter


class ScriptedModel(Model):
    """A fake model that replays predetermined tool calls, one per agent step, and remembers what it was sent."""

    def __init__(self, tool_calls: list[tuple[str, dict]]):
        super().__init__(model_id="scripted-fake-model")
        self._script = iter(tool_calls)
        self.prompts: list[str] = []  # the full model input of each step, as text

    def generate(self, messages, stop_sequences=None, response_format=None, tools_to_call_from=None, **kwargs):
        self.prompts.append(str(messages))
        name, arguments = next(self._script)
        call = ChatMessageToolCall(
            id=f"call_{name}", type="function", function=ChatMessageToolCallFunction(name=name, arguments=arguments)
        )
        return ChatMessage(
            role=MessageRole.ASSISTANT, content="", tool_calls=[call], token_usage=TokenUsage(0, 0)
        )
