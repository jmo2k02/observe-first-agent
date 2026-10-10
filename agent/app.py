from phoenix.otel import register

tracer_provider = register(
    project_name="observe-first-agent",
    auto_instrument=True,  # trace every agent step, model call and tool call
    protocol="http/protobuf",  # send spans to PHOENIX_COLLECTOR_ENDPOINT over HTTP
    set_global_tracer_provider=False,  # trace the agent only, not the chat UI's own web server
)

# Observability first: tracing is registered before anything else is imported, so every
# model call and tool call is traced and sent to Phoenix (PHOENIX_COLLECTOR_ENDPOINT).
# The tools' HTTP client is traced too, so each request to the helpdesk nests under its tool span.
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor  # noqa: E402

from agent.tools import http_client  # noqa: E402

HTTPXClientInstrumentor.instrument_client(http_client, tracer_provider=tracer_provider)

import contextvars  # noqa: E402

from dotenv import load_dotenv  # noqa: E402
from smolagents import GradioUI  # noqa: E402

from agent.helpdesk_agent import build_agent  # noqa: E402


class TracedGradioUI(GradioUI):
    """smolagents' chat UI, keeping one trace per question.

    Gradio advances the streaming agent on a different worker thread for each step, which would lose
    the active span and split one run into several traces. Running every step in the same captured
    context keeps all steps nested under one agent run.
    """

    def _stream_response(self, message, history):
        context = contextvars.copy_context()
        steps = super()._stream_response(message, history)
        while True:
            try:
                yield context.run(next, steps)
            except StopIteration:
                return


# Entry point. Adapted from the Apache-2.0 OpenInference smolagents examples (see NOTICE).
if __name__ == "__main__":
    load_dotenv()  # for the plain-Python fallback; Docker Compose passes .env in directly
    TracedGradioUI(build_agent()).launch(share=False, server_name="0.0.0.0", server_port=7860)
