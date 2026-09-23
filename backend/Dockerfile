FROM python:3.11-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /uvx /bin/

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    OLLAMA_HOST=http://host.docker.internal:11434

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY prism ./prism
COPY data/processed ./data/processed
COPY data/synthetic ./data/synthetic
COPY docker_entrypoint.py ./docker_entrypoint.py

EXPOSE 8000

ENTRYPOINT ["python", "docker_entrypoint.py"]
