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


@tool
def search_knowledge_base(query: str) -> list:
    """
    Search the IT knowledge base for self-help articles with step-by-step fixes (VPN, passwords, printers, laptops).
    Use this when someone reports an IT problem, before opening a ticket. Returns up to three matching articles.

    Args:
        query: A few keywords describing the problem, for example "VPN disconnecting".
    """
    response = http_client.get(f"{_helpdesk_url()}/kb/search", params={"q": query})
    response.raise_for_status()
    return response.json()


@tool
def get_ticket(ticket_id: str) -> dict:
    """
    Get an existing IT support ticket: who opened it, title, description, priority and status.
    Use this when the user asks about a ticket they already have.

    Args:
        ticket_id: The ticket ID, for example "T-1002".
    """
    response = http_client.get(f"{_helpdesk_url()}/tickets/{ticket_id}")
    response.raise_for_status()
    return response.json()


@tool
def create_ticket(employee_id: str, title: str, description: str, priority: str = "medium") -> dict:
    """
    Open a new IT support ticket for an employee. This is the only tool that changes data in the helpdesk.
    Use it when a problem needs IT support. Returns the new ticket with its ticket ID.

    Args:
        employee_id: The ID of the employee who has the problem, for example "E-102".
        title: A short summary of the problem.
        description: What happens, since when, and what was already tried.
        priority: One of "low", "medium" or "high".
    """
    ticket = {"employee_id": employee_id, "title": title, "description": description, "priority": priority or "medium"}
    response = http_client.post(f"{_helpdesk_url()}/tickets", json=ticket)
    response.raise_for_status()
    return response.json()


@tool
def check_service_status(system: str) -> dict:
    """
    Check whether an internal company system is up: "email", "vpn", "payroll" or "printing".
    Always call this first when someone says a system seems broken, down or unavailable,
    even if a ticket was requested: the status decides what the ticket should say.

    Args:
        system: The system name, for example "vpn".
    """
    response = http_client.get(f"{_helpdesk_url()}/status/{system}")
    # An HTTP error (for example 503) raises here: smolagents shows it to the model as a tool error,
    # and the tool span in the trace turns red (ERROR status).
    response.raise_for_status()
    return response.json()


TOOLS = [lookup_employee, search_knowledge_base, get_ticket, create_ticket, check_service_status]

# Name each tool's span in the trace after the tool, instead of smolagents' generic "SimpleTool".
for _tool in TOOLS:
    type(_tool).__name__ = _tool.name
