"""Mock enterprise IT-helpdesk service. The agent's tools call it over HTTP.

All data lives in memory (service/seed.py): new tickets are lost when the service restarts.
"""

import itertools
import re
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from service.seed import EMPLOYEES, KB_ARTICLES, SYSTEMS, TICKETS

app = FastAPI(title="Mock IT Helpdesk")

_next_ticket_number = itertools.count(1001 + len(TICKETS))


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/employees/{employee_id}")
def get_employee(employee_id: str) -> dict:
    employee = EMPLOYEES.get(employee_id.upper())
    if employee is None:
        raise HTTPException(status_code=404, detail=f"No employee with ID {employee_id}")
    return employee


# Small words that appear in many titles ("does not print", "will not connect") and say nothing about the problem.
STOPWORDS = {"and", "are", "can", "does", "for", "has", "have", "into", "keeps", "not", "the", "will", "with", "won"}


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9-]+", text.lower()))


@app.get("/kb/search")
def search_knowledge_base(q: str) -> list[dict]:
    """Simple keyword search: articles ranked by how many query words are whole words of their title or tags."""
    words = {w for w in _words(q) if len(w) > 2 and w not in STOPWORDS}

    def score(article: dict) -> int:
        return len(words & _words(article["title"] + " " + " ".join(article["tags"])))

    ranked = sorted(KB_ARTICLES, key=score, reverse=True)
    return [article for article in ranked if score(article) > 0][:3]


@app.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: str) -> dict:
    ticket = TICKETS.get(ticket_id.upper())
    if ticket is None:
        raise HTTPException(status_code=404, detail=f"No ticket with ID {ticket_id}")
    return ticket


@app.get("/status/{system}")
def service_status(system: str) -> dict:
    """Health of one internal system. Payroll is down on every call: the reproducible demo failure."""
    name = system.lower()
    if name not in SYSTEMS:
        raise HTTPException(status_code=404, detail=f"Unknown system {system}. Known: {', '.join(SYSTEMS)}")
    if name == "payroll":
        raise HTTPException(status_code=503, detail="Payroll system is unavailable")
    return {"system": name, "description": SYSTEMS[name], "status": "healthy"}


class NewTicket(BaseModel):
    employee_id: str
    title: str
    description: str
    priority: Literal["low", "medium", "high"] = "medium"


@app.post("/tickets", status_code=201)
def create_ticket(new: NewTicket) -> dict:
    employee_id = new.employee_id.upper()
    if employee_id not in EMPLOYEES:
        raise HTTPException(status_code=404, detail=f"No employee with ID {new.employee_id}")
    ticket_id = f"T-{next(_next_ticket_number)}"
    TICKETS[ticket_id] = {"id": ticket_id, **new.model_dump(), "employee_id": employee_id, "status": "open"}
    return TICKETS[ticket_id]
