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

KB_ARTICLES = [
    {
        "id": "KB-001",
        "title": "VPN keeps disconnecting or will not connect",
        "tags": ["vpn", "remote", "network", "disconnect", "connection", "home office"],
        "steps": [
            "Check that your internet connection works without the VPN.",
            "Quit the VPN client completely and start it again.",
            "Switch from Wi-Fi to a cable or a mobile hotspot to rule out an unstable network.",
            "Update the VPN client to the latest version from the Software Center.",
            "If it still drops, open a ticket with the time of the last disconnect.",
        ],
    },
    {
        "id": "KB-002",
        "title": "Reset a forgotten password",
        "tags": ["password", "login", "account", "locked", "reset"],
        "steps": [
            "Go to the self-service portal and choose 'Forgot password'.",
            "Confirm with your registered phone number.",
            "If your account is locked after five attempts, wait 15 minutes or open a ticket.",
        ],
    },
    {
        "id": "KB-003",
        "title": "Printer does not print",
        "tags": ["printer", "print", "printing", "queue"],
        "steps": [
            "Check that the printer is on and has paper and toner.",
            "Clear your print queue and send the job again.",
            "Pick the printer by its label on the device, not by an old saved name.",
        ],
    },
    {
        "id": "KB-004",
        "title": "Laptop is slow",
        "tags": ["laptop", "slow", "performance", "computer", "freeze"],
        "steps": [
            "Restart the laptop (at least once a week).",
            "Close browser tabs and apps you do not need.",
            "Install pending updates, then restart again.",
        ],
    },
]

TICKETS = {
    "T-1001": {
        "id": "T-1001",
        "employee_id": "E-101",
        "title": "Second monitor flickers",
        "description": "The external monitor in office 2.14 flickers every few seconds.",
        "priority": "low",
        "status": "in_progress",
    },
    "T-1002": {
        "id": "T-1002",
        "employee_id": "E-102",
        "title": "New laptop for onboarding",
        "description": "Please prepare a laptop for the new payroll trainee starting next month.",
        "priority": "medium",
        "status": "open",
    },
    "T-1003": {
        "id": "T-1003",
        "employee_id": "E-103",
        "title": "Account locked",
        "description": "Locked out after too many password attempts.",
        "priority": "high",
        "status": "closed",
    },
}

# Internal systems the status check knows about. "payroll" is the deliberate failure: the service
# always answers HTTP 503 for it (see service/main.py), so the demo error is the same on every run.
SYSTEMS = {
    "email": "Company email and calendar",
    "vpn": "Remote-access VPN",
    "payroll": "Payroll and salary statements",
    "printing": "Office printers and print queues",
}
