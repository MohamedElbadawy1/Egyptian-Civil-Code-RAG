# 04 - Packaging, Docker & CI/CD

**Status:** Code done, not yet run - no Docker available in the
environment that wrote this
**Date:** 2026-09-26

## What we built
- `Dockerfile` - multi-stage build: a `builder` stage resolves
  dependencies with `uv` and builds the venv, a slim `runtime` stage
  copies only the venv + `src/` + the pre-built corpus JSON, running as a
  non-root user with a `HEALTHCHECK` against `/health`.
- `.dockerignore` - excludes `.venv`, `.git`, `tests/`, `docs/`, and
  critically `.env` (never baked into an image) and `data/raw` (the
  source PDF - not needed at runtime).
- `docker-compose.yml` - local dev convenience: `docker compose up
  --build`, env vars from `.env`, port 8000 exposed.
- `.github/workflows/ci.yml` - added a `docker-build` job (depends on
  `test` passing first) that builds the image with `docker/build-push-action`,
  `push: false` - validates the Dockerfile actually builds on every PR,
  without needing a registry.

## Why / decisions
- **Multi-stage build.** The `builder` stage has `uv` and does dependency
  resolution; the `runtime` stage only copies the finished `.venv` and
  app code - keeps the final image free of build tooling and smaller.
- **`data/raw` excluded, `data/processed` included.** The running API
  only ever reads `data/processed/civil_code_articles.json` (via
  `rag/corpus.py`) - it never touches the raw PDF. Ingestion
  (`scripts/build_corpus.py`) is a one-time offline step run locally, not
  something the deployed API needs to do. Keeps the image smaller and
  keeps "what changes at runtime" separate from "what changes when the
  source document changes."
- **`.env` never baked into the image.** Secrets (OpenAI/Weaviate keys)
  are injected at container start via `env_file` in Compose, or via
  whatever secret mechanism a real deployment target uses later - never
  `COPY`'d into a layer.
- **Non-root user + `HEALTHCHECK`.** Baseline hardening; the healthcheck
  hits the existing `/health` endpoint from Step 03 rather than adding a
  new one.
- **CI builds but doesn't push.** No container registry is configured
  yet (Docker Hub / GHCR / etc.), so the CI job's job right now is purely
  "does the Dockerfile still build" regression protection - pushing is a
  one-line addition (`push: true` + registry login) once there's
  somewhere to push to and a deployment target that would use it.
- **Weaviate is not containerized.** It's the Weaviate Cloud Sandbox
  instance (see `.env`), not a local service - `docker-compose.yml` only
  runs the API.

## How to run
```
docker compose up --build
# then: http://localhost:8000/docs
```
Or without Compose:
```
docker build -t agentic-rag .
docker run --env-file .env -p 8000:8000 agentic-rag
```

## Results / validation
**Not yet validated:** no Docker available in the environment that wrote
this Dockerfile, so it has never actually been built or run. The CI
`docker-build` job is the first real test of it - push this and check
whether that job passes before trusting the image works. Report back
what happens (build succeeds? `/health` and `/ask` work against the
running container?) so this doc can be updated with real results, same
as every other step.

## Known issues / next steps
- No registry configured - image only exists locally / in CI's ephemeral
  build cache right now, nowhere to `docker pull` it from yet.
- No actual deployment target chosen yet (a VM, a PaaS like Render/Fly.io,
  ECS, etc.) - this step only gets the app container-ready, not deployed
  anywhere.
- `uv.lock` is assumed to exist and be committed (needed for
  `uv sync --frozen` in the builder stage) - if it isn't committed yet,
  `git add uv.lock` before this Dockerfile will work.
- Image size not yet measured (`docker images` after a successful build
  would show it) - `python:3.12-slim` plus `weaviate-client`'s `grpcio`
  dependency is probably the biggest contributor if it ends up large.
