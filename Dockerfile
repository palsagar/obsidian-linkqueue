FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /srv
ENV UV_COMPILE_BYTECODE=1

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
RUN uv sync --frozen --no-dev

# SQLite lives on a persistent volume (configure in Coolify)
ENV QUEUE_DB=/data/queue.db
VOLUME /data

EXPOSE 8000
CMD ["uv", "run", "--no-dev", "uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
