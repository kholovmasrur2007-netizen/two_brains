# two_brains v3.0 — самый безопасный AI-агент в мире

[![tests](https://github.com/kholovmasrur2007-netizen/two_brains/actions/workflows/tests.yml/badge.svg)](https://github.com/kholovmasrur2007-netizen/two_brains/actions/workflows/tests.yml)
[![release](https://img.shields.io/github/v/release/kholovmasrur2007-netizen/two_brains?include_prereleases&label=release)](https://github.com/kholovmasrur2007-netizen/two_brains/releases)
[![python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](https://www.python.org/downloads/)
[![docker](https://img.shields.io/badge/docker-compose-2496ED.svg?logo=docker&logoColor=white)](docker-compose.yml)
[![license](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![tests-count](https://img.shields.io/badge/tests-238%20green-brightgreen.svg)](#test)
[![telegram](https://img.shields.io/badge/telegram-bot-26A5E4.svg?logo=telegram&logoColor=white)](README.telegram.md)
[![stars](https://img.shields.io/github/stars/kholovmasrur2007-netizen/two_brains?style=social)](https://github.com/kholovmasrur2007-netizen/two_brains/stargazers)

## Чем мы отличаемся от AutoGPT / BabyAGI / LangChain Agents

| Фича                          | two_brains v3.0 | AutoGPT | BabyAGI | LangChain Agents |
|-------------------------------|:---:|:---:|:---:|:---:|
| **Двойной критик** (correctness + safety) | ✅ | ❌ | ❌ | ❌ |
| Защитный bar `score ≥ 85`      | ✅ | ❌ | ❌ | ❌ |
| Песочница ФС с защитой от traversal | ✅ | ❌ | ❌ | ⚠️ optional |
| Per-user изоляция workspace    | ✅ | ❌ | ❌ | ❌ |
| Wall-clock 300s timeout        | ✅ | ❌ | ❌ | ⚠️ |
| Disk-space pre-flight check    | ✅ | ❌ | ❌ | ❌ |
| Web UI с лайв-стримом          | ✅ | ⚠️ | ❌ | ❌ |
| WebSocket rate limit           | ✅ | ❌ | ❌ | ❌ |
| Audit log + Prometheus metrics | ✅ | ❌ | ❌ | ❌ |
| One-line install (Docker+nginx)| ✅ | ❌ | ❌ | ❌ |
| 238 тестов, CI зелёный         | ✅ | ⚠️ | ❌ | ⚠️ |
| Open-source MIT                | ✅ | ✅ | ✅ | ✅ |

## Демо

Публичная демка на: 👉 **[demo.two-brains.ai](https://demo.two-brains.ai)**

> **⚠ Деплой инструкция:** для запуска под этим доменом нужно
> направить DNS A-запись на VPS (см. [`deploy-demo.sh`](deploy-demo.sh)).
> Пока не настроено — демка вернёт ошибку DNS. Используй локальный
> запуск ниже или собери у себя.

Локально за 5 секунд:
```bash
docker compose up -d --build && open https://localhost
```

## Установка за 2 минуты

Одной строкой:

```bash
curl -fsSL https://raw.githubusercontent.com/kholovmasrur2007-netizen/two_brains/main/install.sh | bash
```

Или ручками:

```bash
git clone https://github.com/kholovmasrur2007-netizen/two_brains
cd two_brains && chmod +x install.sh && ./install.sh
```

Установщик клонирует репо, копирует `.env.example → .env`, поднимает
Docker-стек (app + Postgres + nginx) и открывает интерфейс на
`https://localhost`. Логин по умолчанию: `admin / admin`.

## Telegram-бот

📦 **Готов** — собственный Telegram-бот ставит задачи в API two_brains
и отвечает прямо в чате.

```bash
# 1. Получи токен у @BotFather
# 2. Допиши в .env:
TELEGRAM_BOT_TOKEN=1234567890:ABC...
TWOBRAINS_BOT_USERNAME=bot
TWOBRAINS_BOT_PASSWORD=<твой-пароль-сервисного-аккаунта>

# 3. Запусти:
docker compose --profile bot up -d --build bot
```

Команды бота:

| `/start` | приветствие | `/run <prompt>` | поставить задачу |
|:---|:---|:---|:---|
| `/status` | проверить liveness | `/usage` | остаток квоты |
| `/help` | справка | | |

Подробная инструкция: [README.telegram.md](README.telegram.md)
(BotFather, сервисный аккаунт, профиль `bot` в compose, локальный запуск).

A small 3-brain pipeline that turns a plain-text task into a structured
plan, critiques it, optionally executes it, and exposes the whole flow
through a CLI **and** a live Web UI.

* **Brain 1 — Planner**: prompt → structured plan.
* **Brain 2 — Critic**: plan → structured critique.
* **Brain 3 — Executor**: ready plan → per-step execution report (dry-run by default).
* **Orchestrator**: runs the brains, emits a `FinalResult`, streams phase events.
* **Memory**: keeps the artefacts in memory, optionally persists to JSON.
* **CLI**: `run`, `show`, `history`, `clear`, `demo` — with `--execute`.
* **Web UI**: FastAPI + WebSocket stream, single-file HTML, no build step.

Three providers are registered:

| Provider        | What it does                              | Needs      |
|-----------------|-------------------------------------------|------------|
| `deterministic` | Pure-Python heuristics (default)          | Nothing    |
| `mock`          | LLM path wired to a `MockLLMClient`       | Nothing    |
| `anthropic`     | Real Claude over the Anthropic Messages API | API key + `anthropic` SDK |

Switching is one env variable — see *Using a real LLM* below.

## Install

Python 3.11 or newer.

```bash
cd two_brains
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env   # optional; enables JSON persistence
```

## Run

```bash
# Pre-baked demo task (no input required)
python -m app.main demo

# One-shot with a prompt as an argument
python -m app.main "Build a calculator web app with tests."

# With constraints (repeatable)
python -m app.main -c "single-file" -c "no backend" "Build a calculator."

# Run Brain 3 on the finalised plan (only fires when ready_for_execution)
python -m app.main --execute "Build a small REST API."

# Interactive prompt
python -m app.main

# Pipe a prompt from stdin
echo "Plan a weekend trip" | python -m app.main

# JSON output for scripts
python -m app.main --format json "Build X."

# Work with stored runs
python -m app.main history
python -m app.main show <task_id>
python -m app.main clear --yes
```

## Web UI

Same orchestrator, behind a FastAPI app with a WebSocket live stream.

```bash
python -m app.web                   # http://127.0.0.1:8000
python -m app.web --port 9000       # alternative port
python -m app.web --reload          # dev hot-reload
```

What the UI shows:

* every phase as a coloured badge — Planner / Critic / Executor go from
  *idle* → *running* → *done* in real time
* the plan, critique, recommendation and per-step execution report
  rendered as they arrive over the WebSocket
* a history sidebar fed by `MemoryStore`

Endpoints:

| Method | Path                  | Purpose                                        |
|--------|-----------------------|------------------------------------------------|
| GET    | `/`                   | the single-page UI                             |
| GET    | `/api/providers`      | available planner / critic / executor names    |
| GET    | `/api/history`        | summaries of every stored task                 |
| GET    | `/api/tasks/{id}`     | full `FinalResult` for a task                  |
| POST   | `/api/run`            | run a task synchronously, return `FinalResult` |
| WS     | `/ws/run`             | run a task with live phase events              |

## Brain 3 — Executor

The executor walks the steps of a finalised plan and produces a structured
`ExecutionOutput` (per-step status + summary). It only fires when the plan is
flagged `ready_for_execution`, so an unready plan is never executed by accident.

Three providers, same registry as the other brains:

| Provider        | What it does                                                | Needs                  |
|-----------------|-------------------------------------------------------------|------------------------|
| `deterministic` | Templated dry-run (default). No side effects, no network.   | Nothing                |
| `mock`          | LLM path wired to a `MockLLMClient` with a canned report.   | Nothing                |
| `anthropic`     | Real Claude reasons through every step.                     | API key + SDK          |

Switch with `EXECUTOR_PROVIDER=anthropic` (or per-request override in the Web UI).

## Autonomous mode (Brain 3 = `agent`)

A fourth executor backend turns the pipeline into a Claude-Code-style
autonomous coder: instead of *simulating*, Claude is given a sandboxed
file-tool surface and walks the plan **for real** — reading, writing,
editing files inside `workspace/`.

```bash
python -m app.main agent "Build a single-file Python script that prints the
Fibonacci sequence up to 100 and write it to fib.py."
```

Tools the agent can call (all sandboxed to `workspace/` by default):

| Tool         | Purpose                                                   |
|--------------|-----------------------------------------------------------|
| `read_file`  | Read a UTF-8 file                                         |
| `write_file` | Create or overwrite a file (parent dirs auto-created)     |
| `edit_file`  | Replace a unique substring in an existing file            |
| `list_dir`   | List a directory's entries                                |
| `grep`       | Search a regex across the sandbox tree                    |

Safety bars (high-security mode, the default):

* **Sandbox**: every path is validated by `Sandbox.resolve()` — absolute
  paths, drive prefixes, `..` segments, and resolved paths outside the
  root are refused before any I/O happens.
* **No shell**: no `subprocess`, no network tools. Files only.
* **Iteration cap**: hard stop at 24 model→tool round-trips per run, so
  a hallucinating model cannot loop forever.
* **Sized limits**: 200 KB per file read/write, 50 grep matches max,
  200 directory entries max.
* **Always falls back**: if the Anthropic API errors out or `ANTHROPIC_API_KEY`
  is missing at run time, the deterministic executor takes over so the
  command still terminates with a usable result.

Configure with:

| Variable           | Default               | Purpose                                |
|--------------------|-----------------------|----------------------------------------|
| `AGENT_WORKSPACE`  | `workspace`           | Sandbox root (relative paths only)     |
| `AGENT_MODEL`      | `claude-sonnet-4-6`   | Anthropic model the agent talks to     |
| `ANTHROPIC_API_KEY`| *(unset)*             | Required for the real agent path       |

Exit codes — useful for shell pipelines:

| Code | Meaning                                         |
|------|-------------------------------------------------|
| 0    | Pipeline ran; plan is **ready** to execute      |
| 1    | Pipeline ran; plan **needs revision**           |
| 2    | Error (bad input, missing task, disk failure, …)|
| 130  | Interrupted with Ctrl+C                         |

Chaining example:

```bash
python -m app.main "Ship feature X" && deploy.sh || echo "plan blocked"
```

## Test

```bash
pytest -q
```

Expected: **228 tests pass**. None hit the network.

## Using a real LLM

The pipeline works fully offline with the deterministic or `mock` provider.
To switch to real Claude:

1. Install the SDK (already in `requirements.txt`, but if you skipped it):
   ```bash
   pip install anthropic
   ```

2. Get an API key at [console.anthropic.com](https://console.anthropic.com)
   (new accounts get $5 of free credit).

3. Put it in `.env`:
   ```
   ANTHROPIC_API_KEY=sk-ant-api03-...
   PLANNER_PROVIDER=anthropic
   CRITIC_PROVIDER=anthropic
   ```

4. Run the same commands as before:
   ```bash
   python -m app.main "Build a REST API for a blog"
   ```
   Now Brain 1 and Brain 2 are both real Claude calls.

If the LLM fails (network issue, bad JSON, missing key during `complete()`),
the brains **fall back to the deterministic implementation** automatically —
the pipeline never crashes mid-run.

If `ANTHROPIC_API_KEY` is missing at startup, you get a clean error and
exit code 2 — no silent fallback, no half-configured state.

## Architecture

```
two_brains/
  app/
    main.py                 CLI entry point (argparse, rich)
    config.py               Settings read from env (dataclass, frozen)
    types/
      task.py               TaskInput
      plan.py               PlanOutput
      critique.py           CritiqueOutput + Judgement literal
      execution.py          ExecutionOutput, StepResult, status literals
      result.py             FinalResult (task + plan + critique + execution + verdict)
    brains/
      base.py                    Planner / Critic / Executor Protocols
      __init__.py                build_planner / build_critic / build_executor factories
      brain1_planner.py          Deterministic planner
      brain1_planner_llm.py      LLM-backed planner (any LLMClient)
      brain2_critic.py           Deterministic critic
      brain2_critic_llm.py       LLM-backed critic (any LLMClient)
      brain3_executor.py         Deterministic executor (templated dry-run)
      brain3_executor_llm.py     LLM-backed executor (any LLMClient) + fallback
    core/
      orchestrator.py            TwoBrainOrchestrator + on_event streaming hook
      logger.py                  Rich-backed logger
    memory/
      store.py                   MemoryStore (in-memory + optional JSON)
    llm/
      base.py                    LLMClient ABC + error classes
      __init__.py                get_llm_client factory
      mock.py                    MockLLMClient for tests / offline
      anthropic_client.py        AnthropicClient (lazy SDK import)
    web/
      __main__.py                python -m app.web entry point (uvicorn)
      server.py                  FastAPI app: REST + WebSocket /ws/run
      static/index.html          Single-page UI, vanilla JS, no build step
    utils/
      helpers.py                 new_id()
  tests/
    test_smoke.py                end-to-end pipeline (det + mock)
    test_brain1.py               Deterministic planner
    test_brain1_llm.py           LLM planner + fallback paths
    test_brain2.py               Deterministic critic
    test_brain2_llm.py           LLM critic + fallback paths
    test_brain3.py               Deterministic executor (skipped/risky/empty paths)
    test_brain3_llm.py           LLM executor + fallback paths
    test_brains_factory.py       Provider registry + Protocol conformance
    test_orchestrator_executor.py  Orchestrator's gated executor wiring
    test_iterative_loop.py       Plan → critique → revise loop
    test_llm_mock.py             MockLLMClient
    test_anthropic_client.py     AnthropicClient (fake SDK, no network)
    test_memory.py               Save/get, JSON round-trip, corruption
    test_cli.py                  Parser, dispatch, round-trip through CLI
    test_web_server.py           FastAPI REST + WebSocket end-to-end
```

### Data flow

```
TaskInput ─▶ Planner.create_plan ─▶ PlanOutput
                                       │
                                       ▼
                                Critic.review_plan ─▶ CritiqueOutput
                                       ▲                 │
                                       │                 ▼
             Planner.revise_plan ◀─────┘          accepted? yes ──▶ FinalResult
                    (if planner is a RevisingPlanner,                 │
                     loops up to MAX_ITERATIONS)                      │
                                                                      ▼
                                              (if execute=True and ready)
                                              Executor.execute_plan
                                                      │
                                                      ▼
                                                ExecutionOutput
```

* Deterministic `PlannerBrain` doesn't implement `revise_plan`, so it
  runs exactly once (the critique is informative but can't reshape the plan).
* `LLMPlannerBrain` does implement it — on rejection it gets another
  turn, with the previous plan and the critique included in the prompt.
* The loop stops on `"accepted"` or at `MAX_ITERATIONS` (default 3).
* Every iteration's artefacts are saved to `MemoryStore` in order (latest wins).

### How ready_for_execution is decided

A plan is flagged ready only when **all three** conditions hold:

1. `critique.overall_score >= 85`
2. No `missing_elements`
3. No `contradictions`

These bars belong to the orchestrator, not the critic — that way you
can tighten them without rewriting the critic.

## Extension points

### Planner / Critic Protocols (`app/brains/base.py`)

```python
@runtime_checkable
class Planner(Protocol):
    def create_plan(self, task: TaskInput) -> PlanOutput: ...

@runtime_checkable
class Critic(Protocol):
    def review_plan(self, plan: PlanOutput) -> CritiqueOutput: ...
```

Any class that exposes the right method satisfies the Protocol — no
inheritance required.

### Brain factories (`app/brains/__init__.py`)

```python
build_planner(provider: str = "deterministic") -> Planner
build_critic (provider: str = "deterministic") -> Critic
```

Register new providers by adding an entry to `_PLANNERS` / `_CRITICS`.

### LLM client contract (`app/llm/base.py`)

```python
class LLMClient(ABC):
    @abstractmethod
    def complete(self, system: str, user: str, *,
                 json_mode: bool = False,
                 temperature: float = 0.0,
                 max_tokens: int | None = None) -> str: ...
```

`get_llm_client(provider)` currently dispatches to:

* `mock` → `MockLLMClient` (always available, no dependencies)
* `anthropic` → `AnthropicClient` (requires `ANTHROPIC_API_KEY`)

Every branch imports the provider's SDK lazily so optional dependencies
stay optional.

## Adding another LLM provider

OpenAI is already wired — set `OPENAI_API_KEY` and use
`PLANNER_PROVIDER=openai` / `CRITIC_PROVIDER=openai`.

For a new provider (e.g. local Ollama):

1. Create `app/llm/ollama_client.py` — subclass `LLMClient`, implement
   `complete()`, wrap errors as `LLMProviderError` / `LLMResponseError`.
2. Add a branch to `get_llm_client()` in `app/llm/__init__.py`.
3. Register planner/critic/executor entries in `app/brains/__init__.py`.
4. Nothing else changes — orchestrator, CLI, memory, tests already work
   through the existing Protocols.

## Authentication

Auth is **disabled by default** so fresh installs work immediately. Enable it in `.env`:

```
AUTH_ENABLED=true
USE_DB=true
SECRET_KEY=your-random-secret-here
```

On first start with `AUTH_ENABLED=true` and no users in the DB, the server auto-creates
`admin` / `admin`. Change the password immediately via `POST /auth/register`.

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/auth/login` | POST | Exchange credentials for a JWT token |
| `/auth/register` | POST | Create a new user (admin only) |
| `/auth/me` | GET | Return current user info |
| `/auth/status` | GET | Public — whether auth is enabled |

The Web UI shows a login screen automatically when `AUTH_ENABLED=true`.

## Database

By default the web server uses the JSON-file `MemoryStore`.
Set `USE_DB=true` to switch to **SQLite** (zero-config):

```
USE_DB=true
DATABASE_URL=sqlite:///two_brains.db   # default when USE_DB=true
```

Switch to **PostgreSQL** with one variable:

```
DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/two_brains
```

Install the PostgreSQL adapter separately: `pip install psycopg2-binary`.

## Agent tools

The autonomous executor (`executor_provider=agent` or `local-agent`) can call
7 sandboxed tools, all confined to `workspace/`:

| Tool | Purpose |
|------|---------|
| `read_file` | Read a UTF-8 file |
| `write_file` | Create or overwrite a file |
| `edit_file` | Replace a unique substring |
| `list_dir` | List directory entries |
| `grep` | Regex search across the sandbox |
| `run_python` | Execute a `.py` file, capture output (30s timeout) |
| `run_pytest` | Run pytest on a file or directory (60s timeout) |

Shell execution is sandboxed: only `python` and `pytest` are permitted,
cwd is forced to `workspace/`, and API secrets are stripped from the
child process environment.

## Environment variables

| Variable             | Default              | Purpose |
|----------------------|----------------------|---------|
| `LOG_LEVEL`          | `INFO`               | Root logger level |
| `MAX_ITERATIONS`     | `3`                  | Cap for plan→critique→revise loop |
| `MEMORY_PATH`        | *(unset)*            | JSON memory file (when USE_DB=false) |
| `USE_DB`             | `false`              | Use SQLite/PostgreSQL instead of JSON |
| `DATABASE_URL`       | `sqlite:///two_brains.db` | SQLAlchemy database URL |
| `AUTH_ENABLED`       | `false`              | Require JWT for all API endpoints |
| `SECRET_KEY`         | *(random)*           | JWT signing key — set in production |
| `AUTH_TOKEN_EXPIRE_HOURS` | `24`          | JWT token lifetime |
| `PLANNER_PROVIDER`   | `deterministic`      | Planner implementation |
| `CRITIC_PROVIDER`    | `deterministic`      | Critic implementation |
| `EXECUTOR_PROVIDER`  | `deterministic`      | Executor implementation |
| `ANTHROPIC_API_KEY`  | *(unset)*            | Required for `anthropic` / `agent` providers |
| `OPENAI_API_KEY`     | *(unset)*            | Required for `openai` / `openai-agent` providers |
| `OPENAI_MODEL`       | `gpt-4o-mini`        | OpenAI model for planner/critic/executor |
| `AGENT_WORKSPACE`    | `workspace`          | Sandbox root for the autonomous agent |
| `AGENT_MODEL`        | `claude-sonnet-4-6`  | Anthropic model for the agent loop |

## Production deployment (Docker)

```bash
cp .env.example .env
# edit .env: set SECRET_KEY, ANTHROPIC_API_KEY/OPENAI_API_KEY, etc.

# (optional) generate self-signed TLS cert
mkdir -p nginx/certs && cd nginx/certs
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout server.key -out server.crt -subj "/CN=localhost"
cd ../..

docker compose up -d --build
# https://localhost — login with the auto-created admin/admin user
```

The stack:

* **app** — FastAPI + WebSocket on `:8000`, runs as non-root `appuser`
* **db** — PostgreSQL 16 with persistent volume `pgdata`
* **nginx** — TLS termination, HTTP→HTTPS redirect, WebSocket upgrade,
  internal-only `/metrics`

## Operations endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Liveness probe (always 200 if process is up) |
| GET | `/ready` | Readiness — checks DB connectivity when USE_DB=true |
| GET | `/metrics` | Prometheus text-format counters |
| GET | `/api/usage` | Caller's quota usage today |
| GET | `/api/audit` | Audit log (admin only) — filter by username/action |

Counters surfaced in `/metrics`:

```
two_brains_uptime_seconds          gauge
two_brains_requests_total          counter
two_brains_runs_total              counter
two_brains_runs_failed_total       counter
two_brains_auth_logins_total       counter
two_brains_auth_failures_total     counter
two_brains_quota_exceeded_total    counter
two_brains_rate_limited_total      counter
```

## Status

| Component | State |
|-----------|-------|
| Brain 1 (Planner) — deterministic / LLM / Anthropic / OpenAI | ✅ + fallback |
| Brain 2 (Critic) — deterministic / LLM / Anthropic / OpenAI | ✅ + fallback |
| Brain 3 (Executor) — deterministic / LLM / Anthropic / OpenAI / agent / local-agent / openai-agent | ✅ + fallback |
| Sandboxed shell tools (run_python, run_pytest) | ✅ |
| SQLite / PostgreSQL memory (SQLMemoryStore) | ✅ |
| JWT authentication + per-user accounts | ✅ |
| **Per-user sandbox isolation** (`workspace/<username>/`) | ✅ |
| **Rate limiting** (slowapi, per-IP) | ✅ |
| **Daily per-user task quotas** (DB-backed counter) | ✅ |
| **Audit log** (login / run / register, with admin reader) | ✅ |
| **Health / readiness / Prometheus metrics** | ✅ |
| **Docker + docker-compose stack (web + postgres + nginx)** | ✅ |
| **TLS termination via nginx reverse proxy** | ✅ |
| Web UI (FastAPI + WebSocket + HTML + login screen) | ✅ |
| CLI (run/show/history/clear/demo/agent) | ✅ |
| Orchestrator + iterative revise loop + event streaming | ✅ |
| GitHub Actions CI (Python 3.11 + 3.12) | ✅ |
