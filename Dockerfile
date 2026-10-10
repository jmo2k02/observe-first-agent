# One image for both the agent and the helpdesk service; docker-compose.yml picks the command.
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.24 /uv /bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH"

# Install the exact versions from uv.lock (no surprise upgrades, see README "Why pinned?").
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY agent ./agent
COPY service ./service
