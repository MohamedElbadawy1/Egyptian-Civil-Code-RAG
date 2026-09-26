# syntax=docker/dockerfile:1

# ---- builder: resolve deps + build the venv ----
FROM python:3.12-slim AS builder

RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy only the lock/manifest first so this layer is cached across builds
# that don't touch dependencies -- avoids re-resolving on every code change.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Now copy the actual package + the pre-built corpus the API serves from.
# data/raw (the source PDF) is intentionally NOT copied -- the running API
# only ever reads data/processed/civil_code_articles.json; ingestion is a
# one-time offline step run locally, not part of this image.
COPY src/ ./src/
COPY data/processed/ ./data/processed/
# hatchling (our build backend) reads README.md for project metadata when
# building the package itself -- required even though nothing at runtime
# actually uses this file.
COPY README.md ./
RUN uv sync --frozen --no-dev

# ---- runtime: slim image, no build tooling, non-root user ----
FROM python:3.12-slim AS runtime

RUN useradd --create-home --uid 1000 appuser
WORKDIR /app

COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appuser /app/src /app/src
COPY --from=builder --chown=appuser:appuser /app/data /app/data
COPY --chown=appuser:appuser pyproject.toml ./

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)" || exit 1

CMD ["uvicorn", "agentic_rag.api.main:app", "--host", "0.0.0.0", "--port", "8000"]