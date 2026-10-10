"""Seam A: one agent run end to end, asserting on what lands in the trace."""

import json

import httpx
from opentelemetry.trace import StatusCode

from agent.helpdesk_agent import build_agent
from tests.conftest import ScriptedModel


def test_employee_lookup_is_traced(spans, helpdesk_url):
    model = ScriptedModel(
        [
            ("lookup_employee", {"employee_id": "E-102"}),
            ("final_answer", {"answer": "E-102 is Jonas Weber, Payroll Specialist in Finance."}),
        ]
    )

    answer = build_agent(model).run("Who is employee E-102?")

    assert "Jonas Weber" in str(answer)
    finished = spans.get_finished_spans()

    # The tool span exists and carries the arguments the model chose.
    tool_span = next(s for s in finished if s.name == "lookup_employee")
    assert tool_span.attributes["openinference.span.kind"] == "TOOL"
    assert json.loads(tool_span.attributes["input.value"])["kwargs"] == {"employee_id": "E-102"}
    assert "Jonas Weber" in tool_span.attributes["output.value"]

    # The HTTP request to the helpdesk service is a span nested under the tool span.
    http_span = next(s for s in finished if s.attributes.get("http.url") == f"{helpdesk_url}/employees/E-102")
    assert http_span.name == "GET"
    assert http_span.attributes["http.status_code"] == 200
    assert http_span.parent.span_id == tool_span.context.span_id
    assert http_span.context.trace_id == tool_span.context.trace_id


# The normal-flow prompt from the README.
NORMAL_FLOW_PROMPT = (
    "I'm employee E-102 and my VPN keeps disconnecting every few minutes since this morning. "
    "Please look up my details, search the knowledge base for a fix, and open an IT ticket for me."
)


def test_normal_flow_chains_three_tools(spans, helpdesk_url):
    ticket = {
        "employee_id": "E-102",
        "title": "VPN keeps disconnecting",
        "description": "VPN drops every few minutes since this morning.",
        "priority": "medium",
    }
    model = ScriptedModel(
        [
            ("lookup_employee", {"employee_id": "E-102"}),
            ("search_knowledge_base", {"query": "VPN disconnecting"}),
            ("create_ticket", ticket),
            ("final_answer", {"answer": "Restart the VPN client (KB-001). I opened a ticket for you."}),
        ]
    )

    answer = build_agent(model).run(NORMAL_FLOW_PROMPT)

    assert "KB-001" in str(answer)
    finished = spans.get_finished_spans()
    run_span = next(s for s in finished if s.name == "ToolCallingAgent.run")

    # One tool span per call, each with the arguments the model chose, all in the same trace.
    expected = [
        ("lookup_employee", {"employee_id": "E-102"}, "GET", "/employees/E-102", "Jonas Weber"),
        ("search_knowledge_base", {"query": "VPN disconnecting"}, "GET", "/kb/search?q=VPN+disconnecting", "KB-001"),
        ("create_ticket", ticket, "POST", "/tickets", '"status": "open"'),
    ]
    for name, arguments, method, path, in_output in expected:
        [tool_span] = [s for s in finished if s.name == name]
        assert json.loads(tool_span.attributes["input.value"])["kwargs"] == arguments
        assert in_output in tool_span.attributes["output.value"]
        assert tool_span.context.trace_id == run_span.context.trace_id

        # ... and exactly one HTTP span under it: the request to the helpdesk service.
        [http_span] = [s for s in finished if s.parent and s.parent.span_id == tool_span.context.span_id]
        assert http_span.name == method
        assert http_span.attributes["http.url"] == helpdesk_url + path
        assert http_span.attributes["http.status_code"] in (200, 201)


def test_get_ticket_reads_seed_data(spans, helpdesk_url):
    model = ScriptedModel(
        [
            ("get_ticket", {"ticket_id": "T-1002"}),
            ("final_answer", {"answer": "Ticket T-1002 (new laptop for onboarding) is open."}),
        ]
    )

    answer = build_agent(model).run("What is the status of ticket T-1002?")

    assert "open" in str(answer)
    tool_span = next(s for s in spans.get_finished_spans() if s.name == "get_ticket")
    assert '"status": "open"' in tool_span.attributes["output.value"]


# The payroll error prompt from the README.
PAYROLL_PROMPT = "Payroll seems broken for E-102, check it and open a ticket if needed."


def test_payroll_status_is_always_503(helpdesk_url):
    for _ in range(3):
        assert httpx.get(f"{helpdesk_url}/status/payroll").status_code == 503
    for system in ("email", "vpn", "printing"):
        response = httpx.get(f"{helpdesk_url}/status/{system}")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


def test_payroll_failure_is_a_red_span_and_the_run_still_answers(spans, helpdesk_url):
    ticket = {
        "employee_id": "E-102",
        "title": "Payroll system unavailable",
        "description": "The payroll status check returns HTTP 503.",
        "priority": "high",
    }
    model = ScriptedModel(
        [
            ("check_service_status", {"system": "payroll"}),
            ("create_ticket", ticket),
            ("final_answer", {"answer": "Payroll is down (HTTP 503). I opened a high-priority ticket."}),
        ]
    )

    answer = build_agent(model).run(PAYROLL_PROMPT)

    # The tool error went back to the model and the run still ended with a final answer.
    assert "503" in str(answer)
    finished = spans.get_finished_spans()

    # The payroll check is a tool span with ERROR status that mentions the 503 ...
    [tool_span] = [s for s in finished if s.name == "check_service_status"]
    assert json.loads(tool_span.attributes["input.value"])["kwargs"] == {"system": "payroll"}
    assert tool_span.status.status_code == StatusCode.ERROR
    assert "503" in tool_span.status.description

    # ... with the failed HTTP request nested under it.
    [http_span] = [s for s in finished if s.parent and s.parent.span_id == tool_span.context.span_id]
    assert http_span.attributes["http.url"] == f"{helpdesk_url}/status/payroll"
    assert http_span.attributes["http.status_code"] == 503

    # The agent carried on: the ticket was created after the failure.
    [ticket_span] = [s for s in finished if s.name == "create_ticket"]
    assert ticket_span.status.status_code == StatusCode.OK
