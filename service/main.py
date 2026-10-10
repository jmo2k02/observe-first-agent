"""Mock enterprise IT-helpdesk service. The agent's tools call it over HTTP."""

from fastapi import FastAPI, HTTPException

from service.seed import EMPLOYEES

app = FastAPI(title="Mock IT Helpdesk")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/employees/{employee_id}")
def get_employee(employee_id: str) -> dict:
    employee = EMPLOYEES.get(employee_id.upper())
    if employee is None:
        raise HTTPException(status_code=404, detail=f"No employee with ID {employee_id}")
    return employee
