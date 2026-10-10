"""Mock enterprise IT-helpdesk service. The agent's tools call it over HTTP.

All data lives in memory (service/seed.py): new tickets are lost when the service restarts.
"""

import itertools
import re
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from service.seed import EMPLOYEES, KB_ARTICLES, TICKETS

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


@app.get("/kb/search")
def search_knowledge_base(q: str) -> list[dict]:
    """Simple keyword search: articles ranked by how many query words appear in their title or tags."""
    words = {w for w in re.findall(r"[a-z0-9-]+", q.lower()) if len(w) > 2}

    def score(article: dict) -> int:
        text = (article["title"] + " " + " ".join(article["tags"])).lower()
        return sum(word in text for word in words)

    ranked = sorted(KB_ARTICLES, key=score, reverse=True)
    return [article for article in ranked if score(article) > 0][:3]


@app.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: str) -> dict:
    ticket = TICKETS.get(ticket_id.upper())
    if ticket is None:
        raise HTTPException(status_code=404, detail=f"No ticket with ID {ticket_id}")
    return ticket


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
