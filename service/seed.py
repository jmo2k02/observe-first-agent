"""In-memory seed data for the mock IT helpdesk. Fictional people; resets on every restart."""

EMPLOYEES = {
    "E-101": {
        "id": "E-101",
        "name": "Lena Hoffmann",
        "title": "Head of Finance",
        "department": "Finance",
        "location": "Mannheim",
        "email": "lena.hoffmann@example.com",
        "manager_id": None,
    },
    "E-102": {
        "id": "E-102",
        "name": "Jonas Weber",
        "title": "Payroll Specialist",
        "department": "Finance",
        "location": "Mannheim",
        "email": "jonas.weber@example.com",
        "manager_id": "E-101",
    },
    "E-103": {
        "id": "E-103",
        "name": "Aylin Demir",
        "title": "IT Support Engineer",
        "department": "IT",
        "location": "Heidelberg",
        "email": "aylin.demir@example.com",
        "manager_id": None,
    },
}
