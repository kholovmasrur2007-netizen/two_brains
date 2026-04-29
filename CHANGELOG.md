# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [SemVer](https://semver.org/).

## [2.0.0] — 2026-04-29

The "team-ready" release. Goes from a single-user offline pipeline to
a deployable SaaS-grade system with auth, persistence, sandbox isolation,
rate limiting, audit log and a full Docker stack.

### Added — autonomous agent (third brain)

- **Brain 3 — Executor**: deterministic, LLM-simulated, real-Anthropic
  tool-use, OpenAI tool-use, and offline pattern-matching `local-agent`
  backends. Only fires when the critic blesses the plan (`score >= 85`,
  no missing elements, no contradictions).
- **Sandbox** (`app/sandbox/`): every file operation goes through
  `Sandbox.resolve()` — absolute paths, drive-letter prefixes, `..`
  segments and resolved-paths-outside-root are rejected before any I/O.
- **Tools**: `read_file`, `write_file`, `edit_file`, `list_dir`, `grep`,
  `run_python` (30 s timeout), `run_pytest` (60 s timeout). Subprocess
  env is stripped of API secrets; cwd is forced to the sandbox root.
- **LocalAgentClient** with 25 topic templates (fibonacci, primes,
  bubble/quick sort, FastAPI, calculator, password-gen, tic-tac-toe,
  CSV reader, JSON pretty-printer, todo list, snake game, palindrome,
  FizzBuzz …) and bilingual EN/RU keyword detection.

### Added — Web UI (FastAPI + WebSocket)

- Single-page UI at `GET /`, no build step.
- WebSocket `/ws/run` streams every pipeline phase live:
  `task_received → planner_started → plan_ready → critic_started →
  critique_ready → executor_started → tool_call → tool_result →
  execution_ready → done`, plus `executor_skipped`, `agent_fallback`,
  `error` defensive events.
- `/api/providers`, `/api/run`, `/api/history`, `/api/tasks/{id}`.

### Added — SaaS hardening

- **JWT authentication** (`app/auth/`): `/auth/login`, `/auth/register`
  (admin only), `/auth/me`, `/auth/status`. Disabled by default
  (`AUTH_ENABLED=false`); first run with auth on auto-creates
  `admin/admin`.
- **SQL persistence** (`app/db/`): SQLAlchemy 2.0 store. SQLite
  default, PostgreSQL via `DATABASE_URL=postgresql+psycopg2://...`.
  Tables: `tasks`, `plans`, `critiques`, `results`, `users`,
  `audit_log`, `quotas`.
- **Per-user sandbox isolation**: agent executors get
  `workspace/<username>/` so concurrent users never collide.
- **Rate limiting** (`app/security/rate_limit.py`): slowapi-backed
  per-IP limits — `RATE_LIMIT_GLOBAL`, `RATE_LIMIT_AUTH`,
  `RATE_LIMIT_RUN` env-var overrides.
- **Per-user daily quotas** (`app/security/quotas.py`): atomic
  counter in DB, configurable via `DAILY_TASK_QUOTA`. Exceeded
  requests get `429` with quota details.
- **Audit log** (`app/security/audit.py`): every login / register /
  run / quota-exceeded is recorded with username, IP and target.
  Admin-only `GET /api/audit` with username/action filters.
- **Ops endpoints** (`app/security/health.py`): `/health` (always-200
  liveness), `/ready` (DB connectivity check), `/metrics` (Prometheus
  text format with custom counters).

### Added — deployment

- `Dockerfile` (two-stage build, runs as non-root `appuser`).
- `docker-compose.yml` — web + Postgres 16 + nginx 1.27 stack.
- `nginx/two_brains.conf` — TLS termination, HTTP→HTTPS redirect,
  WebSocket upgrade, `X-Forwarded-Proto`, internal-only `/metrics`.
- `.env.example` — full configuration template.

### Added — providers

- **OpenAI** `OpenAIClient` (Chat Completions) and `OpenAIAgentClient`
  (function calling). Registers `openai`, `openai-agent` providers.
  Drop-in alternative when Anthropic balance is low.

### Added — CLI

- `python -m app.main agent "task"` — autonomous mode end-to-end
  with live tool-call output in the terminal.

### Added — tests

- Test count: **70 → 200+**. New suites: `test_brain3`, `test_brain3_llm`,
  `test_orchestrator_executor`, `test_web_server`, `test_sandbox`,
  `test_agent_executor`, `test_agent_tools_registry`, `test_local_agent`,
  `test_shell_tools`, `test_sql_store`, `test_auth`. CI runs them on
  Python 3.11 + 3.12 with zero network calls.

### Changed

- `Settings` adds `database_url`, `use_db`, `agent_workspace`,
  `agent_model`, `openai_model`. Backwards-compatible defaults.
- `MemoryStore` API is now also implemented by `SQLMemoryStore` —
  the orchestrator and Web server accept either.
- `_make_orchestrator` in the Web server now takes a `username`
  argument and routes file-touching executors to per-user sandboxes.

### Security

- Path-traversal: parametrised tests cover `/etc/passwd`,
  `C:/Windows/...`, `..\\escape`, multi-level `a/b/../../../escape`.
- Username allowlist for sandbox dir names: `[A-Za-z0-9_.-]{1,64}`.
- `Authorization: Bearer` required for every `/api/*` when auth on;
  WebSocket auth carried in the first message.

## [1.0.0] — 2026-04-22

Initial release: 2-brain pipeline (Planner + Critic), Anthropic SDK,
deterministic + mock providers, MemoryStore, CLI, GitHub Actions CI,
70 tests.
