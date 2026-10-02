# 08 - Frontend

**Status:** Done - served and tested locally via TestClient; CI smoke
test added (not yet run - needs a real CI push to confirm)
**Date:** 2026-09-30

## What we built
- `frontend/index.html` - single-file, self-contained (inline CSS/JS, no
  build step, no external dependencies) Arabic RTL chat-style page: a
  question box, a top-k selector, and a results area showing the answer
  plus a chip per cited article (number, relevance score, a visual flag
  for repealed articles).
- `src/agentic_rag/api/main.py` - mounts `frontend/` as static files at
  `/`, **after** every explicit route (`/health`, `/ask`). Starlette
  tries routes in registration order, so the explicit operations still
  match first; the static mount only catches what they don't.
- `Dockerfile` - `COPY frontend/` added to both the builder and runtime
  stages (the image needs it at runtime, not just build time).
- `tests/test_frontend_mount.py` - confirms `/health` and `/docs` aren't
  shadowed by the static mount, and that `/` actually serves HTML.
- `.github/workflows/ci.yml` - `docker-build` job now also starts the
  built image, waits for `/health`, and curls `/` for the page title -
  same "a successful build isn't enough" reasoning as the Step 05 corpus
  smoke test (a missing `COPY frontend/` would still build fine and only
  404 at request time).

## Why / decisions
- **Static HTML/CSS/JS served from FastAPI itself, not a separate
  framework or container.** Chosen specifically for deployment
  simplicity (the person's own stated priority): one Docker image, no
  Node/npm build stage, no CORS handling (same origin), nothing new in
  `docker-compose.yml`. React would need a build stage and likely a
  second container; Streamlit runs its own server process and can't be
  mounted inside FastAPI the way static files can - either would have
  added real deployment complexity for a single-page Q&A UI.
- **Single HTML file, no separate CSS/JS files or framework.** Small
  enough that splitting it up would add navigation overhead without a
  real benefit; keeps the `COPY frontend/` surface in the Dockerfile to
  one directory with one meaningful file in it.
- **Mount registered last, at `/`.** The one real gotcha with this
  approach - mounting a catch-all static directory before the API routes
  are defined would shadow `/ask` and `/health` silently (StaticFiles
  would try to resolve them as files and 404). Verified this ordering
  actually works with a live `TestClient`, not just by reasoning about
  it - see Results below.
- **Repealed articles get a visually distinct chip** (red border/text)
  in the UI, mirroring the `[REPEALED]` flag already in the Step 03
  generation context - so repeal status isn't only in the LLM's prose,
  it's also visible at a glance in the citations list.

## How to run
```bash
uv run python -m uvicorn agentic_rag.api.main:app --host 127.0.0.1 --port 8000
# open http://127.0.0.1:8000/
```
Or via Docker (frontend is baked into the image from Step 04 onward):
```bash
docker compose up --build
```

## Results / validation
Verified locally with a live `TestClient` (not just by reading the code):
- `GET /health` -> 200, still returns `{"status": "ok"}`
- `GET /docs` -> 200, FastAPI's interactive docs still work
- `GET /` -> 200, `text/html`, contains the page title - confirms the
  mount-last ordering actually prevents route shadowing in practice
- `tests/test_frontend_mount.py` (3 tests) passing; full suite 30/30,
  `ruff check` clean

**Not yet validated:** an actual question asked through the browser UI
against the live OpenAI + Weaviate stack (this environment has no network
route to either), and the new CI `docker-build` smoke test steps (never
run in a real CI environment with Docker available). Run it locally, ask
a real question through the page, and push to trigger CI - report back
whether both the manual check and the CI smoke test pass.

## Known issues / next steps
- No loading skeleton/streaming - the page shows a plain "جارٍ البحث..."
  text while waiting; `/ask` isn't currently streamed token-by-token, so
  there's nothing to stream from yet.
- No question history/multi-turn conversation - every question is
  independent, matching `/ask`'s current stateless design (see docs/03).
- No rate limiting or abuse protection on the frontend or `/ask` itself -
  fine for local/demo use, would need addressing before any public
  deployment.
- Arabic font relies on system fonts (`Segoe UI`/Tahoma/Arial) rather
  than a bundled web font - looks fine on Windows/most platforms, worth
  revisiting if it ever needs to look identical everywhere.
