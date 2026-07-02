# Online Auction — Agent Workspace

Build the system described in `docs/system-design.md` as an **MVP first** (the cut defined in
`docs/mvp-scope.md`), then iterate toward the full design. Work **only** inside your kanban workspace.

## Sandbox & workspace — how files persist (READ FIRST)
You run in a Docker sandbox, but your kanban **workspace is a host-mounted, persistent directory**:
`/Users/iliazlobin/Hermes/projects/sd-online-auction-backend-mvp-v2026.07.02.1` — mounted at the **same absolute path** on the host and inside the container. **Do all
work there.** Start every session with `cd "$HERMES_KANBAN_WORKSPACE"`.

HARD RULES (these exact mistakes break runs — do not repeat them):
- **Never relocate work to `/tmp`, bare `/root`, `~`, or any non-mounted path.** Those are container-local
  and ephemeral — invisible on the Mac and lost when the container recycles. Only paths under
  `/Users/iliazlobin/Hermes/projects/sd-online-auction-backend-mvp-v2026.07.02.1` persist.
- **If a tool fails on the environment** (read-only filesystem, missing path, permission denied), **STOP and
  BLOCK the card with the exact error.** Do NOT improvise a new location, copy the repo elsewhere, or
  recreate the card chain — that hides the bug and spawns duplicates.
- **Do not create host cron jobs or host scripts from inside the sandbox** — you cannot write to the host's
  `~/.hermes/scripts`. The host e2e loop is wired host-side by the owner / the final build card.
- Stay in your workspace. Don't touch other projects or host system paths.

## Project structure & code standards (conform to these)
This build must match the shared **System-Design MVP Standards**:
`~/Hermes/docs/SYSTEM-DESIGN-MVP-STANDARDS.md`. Read it before scaffolding. In short:
`src/<pkg>/` layout; **routers → services → models/schemas** layering (routers are thin, no business
logic); `config.py` via `pydantic-settings`; deps in `pyproject.toml` (+ `uv.lock`, dev extras), not a
hand-kept `requirements.txt`; **Alembic** for schema; **multi-stage Dockerfile on `python:3.12-slim`**;
compose services named `db`/`redis`/`app`, only `app` publishes a host port (`${APP_PORT:-8010}:8000`),
healthchecks on all; FastAPI **app factory + lifespan + `GET /healthz`**; white-box tests in `tests/`,
black-box `test_fr<N>_<slug>.py` per requirement in `verify/acceptance/`; ship `.gitignore`, never commit
venvs/`.env`/`*.egg-info`/`*.rdb`. The reference implementation is `projects/whatsapp`.

**Product code is environment-agnostic (HARD).** `src/`, `tests/`, `Dockerfile`, `docker-compose.yml`,
`README.md`, `DEPLOY.md`, `pyproject.toml`, `docs/system-design.md` must contain **zero** references to
Hermes, the sandbox, kanban, `~/Hermes`/`/root/Hermes` paths, or "see AGENTS.md" — a stranger clones it
and runs it. State external needs generically ("requires a running Docker daemon"). Hermes/kanban/sandbox
wiring lives ONLY in `AGENTS.md`, `KICKOFF.md`, and `verify/manifest.env` (the build harness).

## The two specs (read both before building)
| File | Role |
|---|---|
| `docs/system-design.md` | The **full target design**. Source of truth for *where we're going*. |
| `docs/mvp-scope.md` | The **exact cut we build NOW** — stack, scope, the **functional requirements**, the **acceptance criteria**, and the kanban **Build Plan**. Follow it literally. |

If the two conflict for current work, **`docs/mvp-scope.md` wins** — it is the contract for this phase.

## How this gets built (the loop)
Work runs as a **kanban dependency chain** on the **`projects` board**, one role per card, in this shared
workspace (`--workspace dir:/Users/iliazlobin/Hermes/projects/sd-online-auction-backend-mvp-v2026.07.02.1`). The verifier **gates** every milestone: it passes only on
pasted, executed evidence, otherwise it BLOCKs the card straight back to the engineer. See
`docs/mvp-scope.md` → "Build Plan" for the exact cards.

## Roles (kanban assignees)
- `architect` — turns mvp-scope into a concrete `design.md` + file/module layout, **and emits the executable
  acceptance suite** (see below). No app code.
- `senior-engineer` — DEFAULT implementation: scaffold, config, Docker, CRUD/glue, serialization, tests, CLI.
- `staff-engineer` — PREMIUM implementation: core algorithms, data model/migrations, API contracts,
  perf-critical/security paths; the escalation target when a senior card fails the gate twice.
- `verifier` — the quality GATE: runs tests/build/app, checks the acceptance criteria, PASS or BLOCK with evidence.
- `sre` — `docker-compose.yml`, `DEPLOY.md`, `.env.example`, healthchecks; brings the stack up reproducibly.
- `writer` — README + synthesis; documents only evidence-backed commands.

## The acceptance contract — the functional requirements ARE the tests
This is the spine of the build. Treat it as non-negotiable:

- **The architect emits `verify/acceptance/` as a first-class deliverable** — one executable **black-box**
  case per functional requirement in `docs/mvp-scope.md`, asserting real **input → output** (status codes,
  bodies, error cases, idempotency, concurrency) against the *running* system. Base URL comes from
  `API_BASE_URL`. These cases are the fixed contract everything else builds toward.
- **Black-box only.** Acceptance cases talk to the running system over HTTP/CLI and must **not** `import` the
  app. White-box unit tests (that import app modules) live under `tests/` and belong to your sandbox-native
  CI run — never mix them into `verify/acceptance/`.
- **The host e2e loop runs the full suite against the live system.** `~/Hermes/bin/e2e-verify` stands the
  real stack up on the host (the sandbox can't), runs `verify/acceptance/`, and on any failing requirement
  files an idempotency-keyed fix card + capped verifier gate back to this board, naming which requirement
  failed. The final build card wires this (`e2e-verify init` + fill `verify/manifest.env` + run; green-is-ship).
- **NEVER game the gate.** Make the *system* satisfy the requirement. Do **not** edit `verify/manifest.env`
  or `verify/acceptance/*`, `xfail`/skip/loosen a case, or add the app's own deps to `TEST_DEPS` to make a
  test import/pass. If a case genuinely mis-states a requirement, `kanban_block` and explain — never silently
  rewrite it green.

## Evidence gate (how the verifier decides)
- **Execute every command you document and paste the real output.** No reasoning about what output "would be."
- **Verify from a clean checkout / fresh state**, not the dirty build dir — install/seed/first-run bugs only
  surface fresh.
- **The sandbox has no Docker.** `docker compose up/exec` and curls to compose-published host ports cannot be
  run here. Make the *sandbox-verified* path runnable in-container (`pip install -e .[dev]` → migrations →
  launch app → `curl localhost:$PORT` in the same container → `pytest`); reach host services via
  `host.docker.internal`. Keep Docker/compose as a clearly-labeled "host-only, not auto-verified" appendix —
  the host e2e loop is what proves the compose path. **Never fabricate compose/run output** in DEPLOY.md —
  write expected output only when clearly labeled illustrative; the host e2e loop runs it for real.
- **Multi-stage Dockerfile must keep console entry-point scripts on PATH (HARD).** The image's `CMD`
  (`uvicorn …`) and `docker compose run app alembic upgrade head` need the `uvicorn`/`alembic` *scripts*
  resolvable, not just importable modules. **Do NOT `pip install --target=/x .` then `COPY` that dir into
  `site-packages`** — that copies modules but drops the `bin/` entry-point scripts, and a follow-up
  `pip install .` sees deps already satisfied so it never regenerates them → the container crash-loops with
  `exec: "uvicorn": executable file not found in $PATH`. Correct pattern: build into a venv in the builder
  (`python -m venv /opt/venv`, `pip install .`) and `COPY --from=builder /opt/venv /opt/venv` with
  `ENV PATH="/opt/venv/bin:$PATH"`. Sanity even without Docker: the entry-points must come from a real
  `pip install`, not a hand-copied tree.
- **The app package itself must be IMPORTABLE in the image (HARD).** Distinct from the PATH issue above:
  `uvicorn <pkg>.main:app` (and `alembic`, whose `env.py` imports the app) crash-loop with
  `ModuleNotFoundError: No module named '<pkg>'` when the Dockerfile installs only `requirements.txt`
  (dependencies, not the project) and `COPY src/`-copies the package in without ever installing it.
  Fix: **`pip install .`** the project into the builder venv (preferred — with
  `[tool.setuptools.packages.find] where=["src"]` this exposes `<pkg>`), **or**, for a bare src-layout,
  set **`ENV PYTHONPATH=/app/src`** in the runtime stage. Never `pip install -r requirements.txt` as the
  *only* install step. (Netflix/Twitter/Payment each shipped with neither and sat red on the functional
  gate until back-filled.)
- **Alembic is the SOLE schema owner — do NOT `create_all` on startup (HARD).** When CI/deploy runs
  `alembic upgrade head` (the standard), an app that ALSO calls `Base.metadata.create_all()` in its
  FastAPI `lifespan` creates the tables first, so the migration step then fails with
  `DuplicateTableError: relation "<t>" already exists` and the functional gate goes red. Let migrations
  own the schema: drop the `create_all` block (and its now-unused `engine`/`Base` imports). LeetCode's
  `main.py` documents this ("create_all() is deliberately absent"). Twitter/TikTok both shipped with it
  and stuck red on the migration step until removed.
- **Compose must not hardcode host ports that collide with the operator's infra.** On this box `5432`
  (hermes-postgres), `8000`/`8080`, `6379` are taken. Don't publish a host port for a service only the app
  consumes (Postgres/Redis talk over the compose network); make the one service you curl env-overridable with
  a safe default (e.g. `"${APP_PORT:-8010}:8000"`); keep the in-container port unchanged.

## Watch & steer (owner)
`hermes kanban --board projects stats` · `watch` · `comment <id> "<note>"` · `block`/`unblock`/`reassign`.
Dashboard `/kanban`. Pause everything: `hermes gateway stop` (resume: `start`).
