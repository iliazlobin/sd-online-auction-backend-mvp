# Kickoff — build the Online Auction MVP

Prereqs (do these first):
1. Paste the system design into `docs/system-design.md`.
2. Fill `docs/mvp-scope.md` — especially **Functional Requirements** and **Acceptance Criteria** (these become
   the executable `verify/acceptance/` suite, the contract the whole build is measured against).

Then start the build. **Option A** (paste to the `zen` bot) decomposes from your Build Plan; **Option B**
(CLI) is a fully deterministic generic chain. The dispatcher (60s tick) runs the chain on its own; the
verifier gates each milestone and loops back on failure. You're only needed if a card hard-blocks past retries.

---
## Option A — paste this to the zen bot

> Start the **Online Auction MVP** build on the **`projects`** kanban board. First read
> `/Users/iliazlobin/Hermes/projects/sd-online-auction-backend-mvp-v2026.07.02.1/AGENTS.md`, `docs/system-design.md`, and `docs/mvp-scope.md`. Then create the dependency
> chain from `docs/mvp-scope.md` → **Build Plan**: `projects-architect` (design.md + the executable
> `verify/acceptance/` suite, one black-box case per functional requirement) → `projects-senior-engineer`/`projects-staff-engineer`
> build cards → `projects-verifier` (the gate) → `projects-sre` (compose + `verify/manifest.env`) → `projects-writer`. Each card depends
> on the previous and shares `--workspace dir:/Users/iliazlobin/Hermes/projects/sd-online-auction-backend-mvp-v2026.07.02.1`. Make build cards goal-loop. Every file-changing
> card ends with a checkpoint commit (`scaffold:`/`feat:`/`ci:`/`docs:`) + best-effort push. Then let the board
> run — the projects-verifier passes only on pasted evidence and loops back on failure. Message me only on a hard block.
> Reply with the cards you created.

---
## Option B — deterministic generic CLI (run on the Mac host)

```bash
export PATH="$HOME/.local/bin:$PATH"
B="--board projects"
WS="--workspace dir:/Users/iliazlobin/Hermes/projects/sd-online-auction-backend-mvp-v2026.07.02.1"
RD="Read AGENTS.md, docs/system-design.md, and docs/mvp-scope.md first."
jid(){ python3 -c "import sys,json;print(json.load(sys.stdin)['id'])"; }

C1=$(hermes kanban $B create "Architect: design.md + module layout + executable acceptance suite" \
  --assignee projects-architect --goal --goal-max-turns 25 $WS \
  --body "$RD Produce design.md (module/file layout, data flow, API/handler or CLI contracts). Then emit verify/acceptance/ — ONE executable black-box pytest case per Functional Requirement in docs/mvp-scope.md, asserting real input->output (status codes, bodies, error cases, idempotency, concurrency) against the RUNNING system via API_BASE_URL. Do NOT import the app in these cases. Flesh out the Build Plan in docs/mvp-scope.md. No app code yet." --json | jid)

C2=$(hermes kanban $B create "Senior-engineer: scaffold + bring-up + healthz" \
  --assignee projects-senior-engineer --parent $C1 --goal --goal-max-turns 30 --max-retries 3 $WS \
  --body "$RD Implement the scaffold per design.md: repo layout, deps, config/env, docker-compose (if applicable; do NOT hardcode host ports that collide — see AGENTS.md), schema + migrations, a health/seed endpoint or CLI entrypoint. The app/CLI must START and a pytest skeleton must be green. Start it before completing. Checkpoint: git add -A && git commit -m \"scaffold: <summary>\" and push (best-effort; a failed sandbox push is non-fatal)." --json | jid)

C3=$(hermes kanban $B create "Staff-engineer: implement MVP until verify/acceptance passes" \
  --assignee projects-staff-engineer --parent $C2 --goal --goal-max-turns 45 --max-retries 3 $WS \
  --body "$RD Implement the MVP functional requirements per design.md + docs/mvp-scope.md until EVERY case in verify/acceptance/ passes sandbox-native (run the app in-container, reach host services via host.docker.internal or stubs). The acceptance suite is the FIXED contract — make the system satisfy it; do NOT edit/skip/loosen the cases. Paste the passing run. Checkpoint: git add -A && git commit -m \"feat: <FRs>\" and push (best-effort)." --json | jid)

C4=$(hermes kanban $B create "Verifier: GATE — clean checkout, unit tests + acceptance suite, evidence" \
  --assignee projects-verifier --parent $C3 --max-retries 3 $WS \
  --body "$RD From a CLEAN state: run the white-box unit tests AND the black-box verify/acceptance suite against a locally-run instance. Walk every Acceptance Criterion with pasted, executed evidence. PASS with metadata {\"gate\":\"pass\"} only on full evidence; otherwise BLOCK with the exact failures. Never pass on 'looks right'." --json | jid)

C5=$(hermes kanban $B create "SRE: compose polish + DEPLOY.md + .env.example + verify/manifest.env" \
  --assignee projects-sre --parent $C4 --goal --goal-max-turns 25 $WS \
  --body "$RD Make 'clean checkout -> up -> working' reproducible (DEPLOY.md, .env.example names-only, healthchecks; no colliding host ports). ALSO author verify/manifest.env for the host e2e loop: MODE, an isolated UP/DOWN (overridable \$PORT), a READY check hitting a real endpoint, LOGS, TEST_DEPS (black-box client only), and ACCEPTANCE running verify/acceptance against the live \$PORT. Do not run e2e-verify (host-only) — just write a correct manifest. FORMAT (critical — e2e-verify does \`set -a; . manifest.env\`, so it SOURCES the file): every value containing spaces MUST be single-quoted, e.g. \`UP='docker compose up -d --build'\`, \`READY='curl -sf http://localhost:\$PORT/healthz'\`, \`ACCEPTANCE='API_BASE_URL=\"http://localhost:\$PORT\" \"\$PY\" -m pytest verify/acceptance -q'\` — an UNQUOTED multi-word value gets run as a shell command at source-time, leaving the var EMPTY so e2e silently skips it and FALSELY reports PASS. \`TEST_DEPS\` must be SPACE-separated (\`TEST_DEPS='httpx pytest'\`), never comma-separated (pip runs \`pip install \$TEST_DEPS\`). Match the format \`e2e-verify init\` emits. Checkpoint: git add -A && git commit -m \"ci: workflows + deploy + manifest\" and push (best-effort)." --json | jid)

C6=$(hermes kanban $B create "Writer: README + DESIGN.md + cleanup (evidence-backed only)" \
  --assignee projects-writer --parent $C5 --goal --goal-max-turns 20 $WS \
  --body "$RD Write root README.md (what it is, quickstart, architecture, API/CLI summary, CI badges) + DESIGN.md (this build's design + FR<->acceptance-test map + Test scenarios/results with live CI refs; self-contained, NO private links). Fold docs/mvp-scope.md into DESIGN.md; KEEP SPEC.md; delete the build harness (design.md, AGENTS.md, KICKOFF.md, docs/, synthesis.md). Document only commands that appear, passing, in the verifier's evidence. Checkpoint: git add -A && git commit -m \"docs: README + DESIGN + cleanup\" and push (best-effort)." --json | jid)

echo "Created chain: C1=$C1 C2=$C2 C3=$C3 C4=$C4 C5=$C5 C6=$C6"
```

---
## Turn on the host e2e acceptance loop (after the chain is green)
`e2e-verify` is host-only (not in the sandbox), so the owner runs this once the build is green:

```bash
~/Hermes/bin/e2e-verify register /Users/iliazlobin/Hermes/projects/sd-online-auction-backend-mvp-v2026.07.02.1   # join the shared 30m acceptance cron
~/Hermes/bin/e2e-verify run /Users/iliazlobin/Hermes/projects/sd-online-auction-backend-mvp-v2026.07.02.1         # confirm green now; red -> self-files fix cards to projects
```

From then on the shared cron `E2E Verifier (all projects)` re-runs the full acceptance suite against the live
system every 30m and self-files the bounded fix→reverify loop on any regression.

---
## Watch & steer
- `hermes kanban --board projects stats` · `watch` · `comment <id> "<note>"` · `block`/`unblock`/`reassign`
- Dashboard `/kanban`. Pause everything: `hermes gateway stop` (resume: `start`).
