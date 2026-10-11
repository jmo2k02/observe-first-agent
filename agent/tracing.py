"""Observability first: importing this module switches tracing on.

agent/app.py imports it as its very first statement, so every agent step, model call, tool call and
HTTP request to the helpdesk is traced and sent to Phoenix (PHOENIX_COLLECTOR_ENDPOINT).
"""

import os

from opentelemetry.sdk.trace import SpanProcessor, SynchronousMultiSpanProcessor
from opentelemetry.trace import Status, StatusCode
from phoenix.otel import register


class FailedRunsTurnRed(SpanProcessor):
    """Marks an agent run that died with an error as ERROR (red) in the trace.

    Workaround for openinference-instrumentation-smolagents 0.1.43: when a streamed run (the chat) raises,
    for example on a rate limit, it records the exception on the run span but then still marks the span OK.
    """

    def on_end(self, span):
        exceptions = [event for event in span.events if event.name == "exception"]
        if span.attributes.get("openinference.span.kind") == "AGENT" and exceptions:
            message = exceptions[-1].attributes.get("exception.message", "")
            span._status = Status(StatusCode.ERROR, message)  # runs before the span is exported


processors = SynchronousMultiSpanProcessor()
processors.add_span_processor(FailedRunsTurnRed())  # first, so it runs before the Phoenix exporter

tracer_provider = register(
    project_name="observe-first-agent",
    auto_instrument=True,  # trace every agent step, model call and tool call
    protocol="http/protobuf",  # send spans to PHOENIX_COLLECTOR_ENDPOINT over HTTP
    set_global_tracer_provider=False,  # trace the agent only, not the chat UI's own web server
    active_span_processor=processors,
    verbose=False,
)
print(f"Tracing is on: project observe-first-agent, sent to {os.getenv('PHOENIX_COLLECTOR_ENDPOINT', 'http://localhost:6006')}")

# The tools' HTTP client is traced too, so each request to the helpdesk nests under its tool span.
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor  # noqa: E402

from agent.tools import http_client  # noqa: E402

HTTPXClientInstrumentor.instrument_client(http_client, tracer_provider=tracer_provider)
