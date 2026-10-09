FROM python:3.12-slim

RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.8.12 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Install locked dependencies before copying frequently changed application code.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY README.md main.py ./
COPY app/ ./app/
RUN uv sync --locked --no-dev \
    && /app/.venv/bin/python -c "import pypdf" \
    && useradd --system --uid 10001 --create-home app \
    && mkdir -p /app/books/metadata \
    && chown -R app:app /app/books

ENV PATH="/app/.venv/bin:$PATH"

USER app

CMD ["python", "main.py"]