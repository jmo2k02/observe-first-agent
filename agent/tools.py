"""Agent tools. Each one is a thin HTTP client for the helpdesk service, so every call shows up as an HTTP span."""

import os

import httpx
from smolagents import tool


# One shared HTTP client for all tools. agent/app.py instruments it, so every request becomes
# a span nested under its tool span (and the chat UI's own HTTP traffic stays out of the trace).
http_client = httpx.Client(timeout=10)


def _request(method: str, path: str, **kwargs):
    """Call the helpdesk service and return its JSON answer.

    An HTTP error (for example 503) raises: smolagents shows the message to the model as a tool error,
    and the tool span in the trace turns red (ERROR status). The message includes the service's own
    explanation ("detail"), so the model and the trace both see why the call failed.
    """
    response = http_client.request(method, os.getenv("HELPDESK_URL", "http://localhost:8000") + path, **kwargs)
    if response.is_error:
        try:
            detail = response.json()["detail"]
        except (ValueError, KeyError, TypeError):  # not the service's usual {"detail": ...} error body
            detail = response.text
        message = f"{response.status_code} {response.reason_phrase}: {detail}"
        raise httpx.HTTPStatusError(message, request=response.request, response=response)
    return response.json()


@tool
def lookup_employee(employee_id: str) -> dict:
    """
    Look up an employee in the company directory: name, job title, department, location, email and manager.
    Use this whenever the user asks who someone is or needs details about a colleague.

    Args:
        employee_id: The employee ID, for example "E-102".
    """
    return _request("GET", f"/employees/{employee_id}")


@tool
def search_knowledge_base(query: str) -> list:
    """
    Search the IT knowledge base for self-help articles with step-by-step fixes (VPN, passwords, printers, laptops).
    Use this when someone reports an IT problem, before opening a ticket. Returns up to three matching articles.

    Args:
        query: A few keywords describing the problem, for example "VPN disconnecting".
    """
    return _request("GET", "/kb/search", params={"q": query})


@tool
def get_ticket(ticket_id: str) -> dict:
    """
    Get an existing IT support ticket: who opened it, title, description, priority and status.
    Use this when the user asks about a ticket they already have.

    Args:
        ticket_id: The ticket ID, for example "T-1002".
    """
    return _request("GET", f"/tickets/{ticket_id}")


@tool
def create_ticket(employee_id: str, title: str, description: str, priority: str = "medium") -> dict:
    """
    Open a new IT support ticket for an employee. This is the only tool that changes data in the helpdesk.
    Use it when a problem needs IT support. Returns the new ticket with its ticket ID.

    Args:
        employee_id: The ID of the employee who has the problem, for example "E-102".
        title: A short summary of the problem.
        description: What happens, since when, and what was already tried.
        priority: One of "low", "medium" or "high" (any other value is rejected). Defaults to "medium".
    """
    priority = (priority or "medium").strip().lower()  # accept "High" or " high " too
    ticket = {"employee_id": employee_id, "title": title, "description": description, "priority": priority}
    return _request("POST", "/tickets", json=ticket)


@tool
def check_service_status(system: str) -> dict:
    """
    Check whether an internal company system is up: "email", "vpn", "payroll" or "printing".
    Always call this first when someone says a system seems broken, down or unavailable,
    even if a ticket was requested: the status decides what the ticket should say.

    Args:
        system: The system name, for example "vpn".
    """
    return _request("GET", f"/status/{system}")  # payroll answers 503: see _request


TOOLS = [lookup_employee, search_knowledge_base, get_ticket, create_ticket, check_service_status]

# Name each tool's span in the trace after the tool, instead of smolagents' generic "SimpleTool".
for _tool in TOOLS:
    type(_tool).__name__ = _tool.name
