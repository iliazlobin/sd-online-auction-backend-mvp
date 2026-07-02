# Online Auction — MVP Scope (the contract for what we build NOW)

This file is the **contract**. The architect turns it into `design.md` + the executable
`verify/acceptance/` suite; the verifier gates against the Acceptance Criteria below. Be concrete.

## Stack
> The lean stack for the MVP (language, framework, datastore, key libs). Prefer the smallest thing that
> meets the functional requirements. Example: Python 3.11 · FastAPI · PostgreSQL · httpx · pytest · Docker Compose.

## Scope
**In (build now):**
> - …

**Out (later phases):**
> - …

## Functional Requirements
> Number each requirement. Each becomes one executable black-box acceptance case (input → expected output).
> Be specific about status codes, payloads, error cases, idempotency, and concurrency.

- **FR-1** — …
- **FR-2** — …
- **FR-3** — …

## Acceptance Criteria
> One per functional requirement, phrased as an assertion the verifier can EXECUTE against the running system.
> These map 1:1 to files under `verify/acceptance/`.

- **AC-1 (FR-1)** — `GET /… → 200` with `{…}`; unknown id → `404`.
- **AC-2 (FR-2)** — …
- **AC-3 (FR-3)** — …

## Build Plan
> The kanban dependency chain. The generic chain in KICKOFF.md (Option B) works as-is; refine it here if the
> build needs domain-specific engineer cards. Pattern:
> architect → senior/staff-engineer build cards → verifier GATE → sre (compose + verify/manifest.env) → writer,
> then the owner turns on the host e2e loop.
