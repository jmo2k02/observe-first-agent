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
from openinference.instrumentation.smolagents import SmolagentsInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from smolagents import ChatMessage, MessageRole, Model
from smolagents.models import ChatMessageToolCall, ChatMessageToolCallFunction
from smolagents.monitoring import TokenUsage

from agent.tools import http_client
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


@pytest.fixture
def spans(helpdesk_url):
    """Trace like agent/app.py does (smolagents + the tools' HTTP client), but into memory instead of Phoenix."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    SmolagentsInstrumentor().instrument(tracer_provider=provider)
    HTTPXClientInstrumentor.instrument_client(http_client, tracer_provider=provider)
    yield exporter
    HTTPXClientInstrumentor.uninstrument_client(http_client)
    SmolagentsInstrumentor().uninstrument()


class ScriptedModel(Model):
    """A fake model that replays predetermined tool calls, one per agent step."""

    def __init__(self, tool_calls: list[tuple[str, dict]]):
        super().__init__(model_id="scripted-fake-model")
        self._script = iter(tool_calls)

    def generate(self, messages, stop_sequences=None, response_format=None, tools_to_call_from=None, **kwargs):
        name, arguments = next(self._script)
        call = ChatMessageToolCall(
            id=f"call_{name}", type="function", function=ChatMessageToolCallFunction(name=name, arguments=arguments)
        )
        return ChatMessage(
            role=MessageRole.ASSISTANT, content="", tool_calls=[call], token_usage=TokenUsage(0, 0)
        )
