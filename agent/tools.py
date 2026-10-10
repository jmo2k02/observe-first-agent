"""Agent tools. Each one is a thin HTTP client for the helpdesk service, so every call shows up as an HTTP span."""

import os

import httpx
from smolagents import tool


# One shared HTTP client for all tools. agent/app.py instruments it, so every request becomes
# a span nested under its tool span (and the chat UI's own HTTP traffic stays out of the trace).
http_client = httpx.Client(timeout=10)


def _helpdesk_url() -> str:
    return os.getenv("HELPDESK_URL", "http://localhost:8000")


@tool
def lookup_employee(employee_id: str) -> dict:
    """
    Look up an employee in the company directory: name, job title, department, location, email and manager.
    Use this whenever the user asks who someone is or needs details about a colleague.

    Args:
        employee_id: The employee ID, for example "E-102".
    """
    response = http_client.get(f"{_helpdesk_url()}/employees/{employee_id}")
    response.raise_for_status()
    return response.json()


TOOLS = [lookup_employee]

# Name each tool's span in the trace after the tool, instead of smolagents' generic "SimpleTool".
for _tool in TOOLS:
    type(_tool).__name__ = _tool.name
