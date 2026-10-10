"""Seam A: one agent run end to end, asserting on what lands in the trace."""

import json

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
