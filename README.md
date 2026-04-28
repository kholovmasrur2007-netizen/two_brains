# two_brains

[![tests](https://github.com/kholovmasrur2007-netizen/two_brains/actions/workflows/tests.yml/badge.svg)](https://github.com/kholovmasrur2007-netizen/two_brains/actions/workflows/tests.yml)
[![python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![license](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

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

Expected: **142 tests pass**. None hit the network.

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

Say you want OpenAI:

1. Create `app/llm/openai_client.py` — subclass `LLMClient`, implement
   `complete()`, wrap SDK errors as `LLMProviderError`, reject unusable
   responses as `LLMResponseError`.
2. Add a branch to `get_llm_client()`:
   ```python
   if provider == "openai":
       from app.llm.openai_client import OpenAIClient
       from app import config
       return OpenAIClient(api_key=config.settings.openai_api_key)
   ```
3. Register factory entries in `app/brains/__init__.py`:
   ```python
   def _openai_planner() -> Planner:
       from app.llm import get_llm_client
       return LLMPlannerBrain(llm=get_llm_client("openai"))
   # same for _openai_critic
   _PLANNERS["openai"] = _openai_planner
   _CRITICS["openai"]  = _openai_critic
   ```
4. Nothing else changes — orchestrator, CLI, memory, tests already work
   through the existing Protocols.

## Environment variables

All optional; defaults are sensible for local use.

| Variable             | Default          | Purpose                                       |
|----------------------|------------------|-----------------------------------------------|
| `LOG_LEVEL`          | `INFO`           | Root logger level                             |
| `MAX_ITERATIONS`     | `3`              | Cap for the iterative plan→critique→revise loop |
| `MEMORY_PATH`        | *(unset)*        | JSON file to mirror `MemoryStore` state       |
| `PLANNER_PROVIDER`   | `deterministic`  | Which planner implementation to build         |
| `CRITIC_PROVIDER`    | `deterministic`  | Which critic implementation to build          |
| `EXECUTOR_PROVIDER`  | `deterministic`  | Which executor implementation to build        |
| `LLM_PROVIDER`       | `none`           | Which LLM backend to use (not wired yet)      |
| `OPENAI_API_KEY`     | *(unset)*        | Read by future OpenAI client                  |
| `ANTHROPIC_API_KEY`  | *(unset)*        | Read by `AnthropicClient`                     |
| `LOCAL_LLM_URL`      | *(unset)*        | Read by future local-model client             |

## Status

| Component                              | State                     |
|----------------------------------------|---------------------------|
| Brain 1 (Planner, deterministic + LLM) | implemented + fallback    |
| Brain 2 (Critic, deterministic + LLM)  | implemented + fallback    |
| Brain 3 (Executor, deterministic + LLM)| implemented + fallback    |
| `MockLLMClient`                        | implemented               |
| `AnthropicClient`                      | implemented               |
| Orchestrator + iterative revise loop   | implemented               |
| Orchestrator event streaming hook      | implemented               |
| Memory (in-process + JSON)             | implemented               |
| CLI (run/show/history/clear/demo + --execute) | implemented        |
| Web UI (FastAPI + WebSocket + HTML)    | implemented               |
| GitHub Actions CI                      | implemented               |
| Autonomous agent executor (sandboxed file tools) | implemented + fallback |
| Shell / subprocess execution           | not yet (high-security mode) |
| Other LLM providers (OpenAI, local)    | contract ready, not wired |
