"""Observability first: importing this module switches tracing on.

agent/app.py imports it as its very first statement, so every agent step, model call, tool call and
HTTP request to the helpdesk is traced and sent to Phoenix (PHOENIX_COLLECTOR_ENDPOINT).
"""

import os
import warnings

from dotenv import load_dotenv
from opentelemetry.sdk.trace import SpanProcessor, SynchronousMultiSpanProcessor
from opentelemetry.trace import Status, StatusCode
from phoenix.otel import register

# Read .env first, so its settings apply to the tracing set-up below (Docker Compose passes them in directly).
load_dotenv(".env")


class FailedRunsTurnRed(SpanProcessor):
    """Marks an agent run that died with an error as ERROR (red) in the trace.

    Workaround for a bug in openinference-instrumentation-smolagents 0.1.43 (the version pinned in
    pyproject.toml): when a streamed run (the chat) raises, for example on a rate limit, _RunWrapper records
    the exception on the run span, but its `finally:` block then calls span.set_status(OK) anyway.
    Check whether this is still needed when you upgrade that package.
    """

    warned = False

    def on_end(self, span):
        exceptions = [event for event in span.events if event.name == "exception"]
        if span.attributes.get("openinference.span.kind") != "AGENT" or not exceptions:
            return
        # An ended span is read-only, so this writes OpenTelemetry's private _status field. It works because
        # this processor runs before the exporter. If a new OpenTelemetry version renames the field, say so.
        if not hasattr(span, "_status"):
            if not self.warned:
                warnings.warn("FailedRunsTurnRed: spans have no _status field any more, failed runs stay green")
                self.warned = True
            return
        message = exceptions[-1].attributes.get("exception.message", "")
        span._status = Status(StatusCode.ERROR, message)


processors = SynchronousMultiSpanProcessor()
processors.add_span_processor(FailedRunsTurnRed())  # first, so it runs before the Phoenix exporter

tracer_provider = register(
    project_name="observe-first-agent",
    auto_instrument=True,  # trace every agent step, model call and tool call
    protocol="http/protobuf",  # send spans to PHOENIX_COLLECTOR_ENDPOINT over HTTP
    batch=True,  # send spans in the background, so the agent never waits for Phoenix
    set_global_tracer_provider=False,  # trace the agent only, not the chat UI's own web server
    active_span_processor=processors,
    verbose=False,
)
print(f"Tracing is on: project observe-first-agent, sent to {os.getenv('PHOENIX_COLLECTOR_ENDPOINT', 'http://localhost:6006')}")

# The tools' HTTP client is traced too, so each request to the helpdesk nests under its tool span.
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor  # noqa: E402

from agent.tools import http_client  # noqa: E402

HTTPXClientInstrumentor.instrument_client(http_client, tracer_provider=tracer_provider)
