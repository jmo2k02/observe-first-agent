"""Seam A through the chat: what a student sees in the web chat, and what lands in the trace."""

import logging
import threading
import time

import pytest
from opentelemetry.trace import StatusCode

from agent.app import build_ui
from agent.helpdesk_agent import build_agent, build_model
from tests.conftest import ScriptedModel


def ask(ui, question):
    """Send one chat message and return the chat messages shown at the end."""
    messages = []
    for messages in ui._stream_response(question, history=[]):
        pass
    return messages


def test_every_question_is_an_independent_run(spans, helpdesk_url):
    model = ScriptedModel(
        [
            ("lookup_employee", {"employee_id": "E-102"}),
            ("final_answer", {"answer": "E-102 is Jonas Weber."}),
            ("check_service_status", {"system": "vpn"}),
            ("final_answer", {"answer": "The VPN is healthy."}),
        ]
    )
    ui = build_ui(build_agent(model))

    ask(ui, "Who is employee E-102?")
    ask(ui, "Is the VPN up?")

    # The second run's model input holds nothing from the first conversation ...
    second_run_prompts = model.prompts[2:]
    assert all("Who is employee" not in prompt and "Jonas Weber" not in prompt for prompt in second_run_prompts)
    # ... and each question is its own trace.
    runs = [s for s in spans.get_finished_spans() if s.name == "ToolCallingAgent.run"]
    assert len(runs) == 2
    assert runs[0].context.trace_id != runs[1].context.trace_id


def test_daily_quota_error_shows_in_the_chat_at_once_and_the_run_is_red(spans, monkeypatch):
    model = build_model()  # the real OpenRouter model, with the network call replaced by a 429
    calls = []

    def quota_exhausted(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("litellm.RateLimitError: OpenrouterException - Rate limit exceeded: free-models-per-day")

    monkeypatch.setattr(model.client, "completion", quota_exhausted)
    ui = build_ui(build_agent(model))

    started = time.monotonic()
    messages = ask(ui, "Who is employee E-102?")

    # No waiting and no retry for the daily quota: the error is the last chat message.
    assert time.monotonic() - started < 5
    assert len(calls) == 1
    assert "The run failed" in messages[-1].content
    assert "free-models-per-day" in messages[-1].content

    # The top of the trace shows the failure too.
    [run] = [s for s in spans.get_finished_spans() if s.name == "ToolCallingAgent.run"]
    assert run.status.status_code == StatusCode.ERROR
    assert "free-models-per-day" in run.status.description


def test_short_rate_limit_is_retried_once(monkeypatch):
    model = build_model()
    calls = []

    def rate_limited(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("litellm.RateLimitError: 429 Too Many Requests, temporarily rate-limited upstream")

    monkeypatch.setattr(model.client, "completion", rate_limited)
    monkeypatch.setattr("smolagents.utils.time.sleep", lambda seconds: calls.append(seconds))

    with pytest.raises(RuntimeError, match="429"):
        model.generate([{"role": "user", "content": "hi"}])
    assert calls[1] == 5  # one wait of 5 seconds between the two attempts
    assert len(calls) == 3


def test_closing_the_chat_mid_run_ends_the_trace_cleanly(spans, helpdesk_url, caplog):
    model = ScriptedModel(
        [
            ("lookup_employee", {"employee_id": "E-102"}),
            ("search_knowledge_base", {"query": "VPN"}),
            ("final_answer", {"answer": "done"}),
        ]
    )
    stream = build_ui(build_agent(model))._stream_response("Who is employee E-102?", history=[])

    # Gradio runs each step on a worker thread and may close the stream from another one (browser closed).
    worker = threading.Thread(target=next, args=(stream,))
    worker.start()
    worker.join()
    with caplog.at_level(logging.ERROR):
        stream.close()

    assert "Failed to detach context" not in caplog.text
    assert [s.name for s in spans.get_finished_spans() if s.name == "ToolCallingAgent.run"] == ["ToolCallingAgent.run"]
