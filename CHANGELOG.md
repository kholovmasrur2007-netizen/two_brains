# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [SemVer](https://semver.org/).

## [3.0.0] — 2026-04-29

The "world-leader" release. Builds on v2.0's SaaS foundation by adding
the four production-grade safety nets that separate a deployable team
tool from an agent that can be trusted with autonomous execution on
real hardware.

### Added — Brain 2 dual critic

- **`SafetyCritic`** (`app/brains/brain2_critic_safety.py`) — a
  deterministic, regex-driven safety pass. Scans every step + risk +
  objective for dangerous tokens (`rm -rf`, `sudo`, `chmod 777`,
  `curl|wget`, `subprocess`/`os.system`, `python -m http.server`),
  sandbox-traversal (`../`, `/c:`, drive-letter prefixes), module-not-
  found / unknown-command hints, fuzzy success criteria
  (`should work`, `hopefully`, `maybe`), and writes-without-declared-
  risks. Each finding deducts points; final score caps at 100, floors
  at 0; judgement maps from the score using the same thresholds the
  orchestrator already enforces.
- **Dual-critic orchestrator**: every iteration of the
  plan→critique loop runs both the primary critic and the
  `SafetyCritic`. The combined critique inherits
  `min(primary.score, safety.score)`, the union of weaknesses /
  missing / contradictions / risk_flags, and a recomputed
  `final_judgement`. A confident-sounding correctness pass can no
  longer override a safety failure. Toggleable via
  `enable_dual_critic=True` (default) on `TwoBrainOrchestrator`.

### Added — runtime safety nets

- **300 s wall-clock timeout** in `AgentExecutorBrain`. The agent loop
  checks `time.monotonic()` against a deadline at the start of every
  iteration; on overrun it halts cleanly with `halted_reason="timeout"`,
  populates a partial trace, and the deterministic fallback never
  kicks in — the failure surfaces as a `failed` ExecutionOutput.
- **Disk-space pre-flight in `write_file`**. Before opening the file
  the sandbox calls `shutil.disk_usage(root).free`; if the encoded
  payload is bigger, the call fails with a clear Russian-language
  `SandboxError` ("Недостаточно места: нужно X, свободно Y"). This
  closes the "fill-the-disk" DoS class.
- **WebSocket per-IP rate limit**. slowapi covers REST only; for
  `/ws/run` we keep an in-memory sliding window: 10 connections per
  IP per 60 seconds, otherwise the upgrade is closed with code 1008
  "Rate limit exceeded".

### Added — distribution

- **`install.sh`** — one-line installer (`curl | bash`) that clones
  the repo, copies `.env.example` to `.env`, and brings the
  docker-compose stack up.
- **`deploy-demo.sh`** — VPS-side deploy: clones to `/opt/two-brains`,
  generates a 32-byte JWT secret, prompts for API keys, switches
  AUTH_ENABLED + USE_DB on, generates a self-signed TLS cert if none
  exists, and runs `docker compose up -d --build`.
- **`POST.md`** — drop-in announcement copy for LinkedIn / Хабр /
  Twitter / Hacker News in both Russian and English.
- **`.github/workflows/plan-review.yml`** — PR action that runs the
  pipeline on `plan.txt` changes and posts the dual-critic verdict
  back as a comment. Uses deterministic providers — no API credits
  needed in CI.

### Tests

- 228 → **238 (+10)**. New file: `tests/test_brain2_safety.py`
  covers safe plan, `rm -rf`, `sudo`, `curl|wget`, `..` traversal,
  fuzzy success criteria, writes-without-risks, and compounding
  multi-pattern penalties. `tests/test_brains_factory.py` adds an
  assertion that the `safety` provider is registered.

### Changed

- README rewrites: title becomes "two_brains v3.0 — самый безопасный
  AI-агент в мире", adds GitHub Actions / release / Python /
  Docker / license / tests / stars badges, comparison table vs
  AutoGPT / BabyAGI / LangChain Agents, install-in-2-minutes section,
  Telegram-bot-coming-soon teaser.
- Dangerous-pattern penalty in `SafetyCritic` is now -20 (was -15)
  so a single hit reliably drops a plan below the 85-point execution
  bar.

### Security

- Safety critic catches dangerous tokens *and* combines with the
  primary critic via `min()` — even a perfect correctness score
  can't override `rm -rf`.
- WebSocket rate limit closes the gap slowapi (REST-only) leaves
  open.
- Disk-space pre-flight prevents a runaway agent from filling the
  host filesystem.

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
