# two_brains

A small 2-brain pipeline that turns a plain-text task into a structured
plan, critiques it, and returns a single "ready / not ready" verdict.

* **Brain 1 — Planner**: prompt → structured plan.
* **Brain 2 — Critic**: plan → structured critique.
* **Orchestrator**: runs both, emits a `FinalResult`.
* **Memory**: keeps the artefacts in memory, optionally persists to JSON.
* **CLI**: `run`, `show`, `history`, `clear`, `demo`.

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

Expected: **61 tests pass**. None hit the network.

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
      result.py             FinalResult (task + plan + critique + verdict)
    brains/
      base.py                    Planner / Critic Protocols
      __init__.py                build_planner / build_critic factories
      brain1_planner.py          Deterministic planner
      brain1_planner_llm.py      LLM-backed planner (any LLMClient)
      brain2_critic.py           Deterministic critic
      brain2_critic_llm.py       LLM-backed critic (any LLMClient)
    core/
      orchestrator.py            TwoBrainOrchestrator
      logger.py                  Rich-backed logger
    memory/
      store.py                   MemoryStore (in-memory + optional JSON)
    llm/
      base.py                    LLMClient ABC + error classes
      __init__.py                get_llm_client factory
      mock.py                    MockLLMClient for tests / offline
      anthropic_client.py        AnthropicClient (lazy SDK import)
    utils/
      helpers.py                 new_id()
  tests/
    test_smoke.py                end-to-end pipeline (det + mock)
    test_brain1.py               Deterministic planner
    test_brain1_llm.py           LLM planner + fallback paths
    test_brain2.py               Deterministic critic
    test_brain2_llm.py           LLM critic + fallback paths
    test_brains_factory.py       Provider registry + Protocol conformance
    test_llm_mock.py             MockLLMClient
    test_anthropic_client.py     AnthropicClient (fake SDK, no network)
    test_memory.py               Save/get, JSON round-trip, corruption
    test_cli.py                  Parser, dispatch, round-trip through CLI
```

### Data flow

```
TaskInput ─▶ Planner.create_plan ─▶ PlanOutput
                                       │
                                       ▼
                                Critic.review_plan ─▶ CritiqueOutput
                                                         │
                                                         ▼
                                                    FinalResult
                                                 (ready_for_execution,
                                                  final_recommendation)
```

Every artefact is saved to the `MemoryStore` in the order produced.

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

| Variable            | Default          | Purpose                                    |
|---------------------|------------------|--------------------------------------------|
| `LOG_LEVEL`         | `INFO`           | Root logger level                          |
| `MAX_ITERATIONS`    | `3`              | Reserved for the future iterative loop     |
| `MEMORY_PATH`       | *(unset)*        | JSON file to mirror `MemoryStore` state    |
| `PLANNER_PROVIDER`  | `deterministic`  | Which planner implementation to build      |
| `CRITIC_PROVIDER`   | `deterministic`  | Which critic implementation to build       |
| `LLM_PROVIDER`      | `none`           | Which LLM backend to use (not wired yet)   |
| `OPENAI_API_KEY`    | *(unset)*        | Read by future OpenAI client               |
| `ANTHROPIC_API_KEY` | *(unset)*        | Read by future Anthropic client            |
| `LOCAL_LLM_URL`     | *(unset)*        | Read by future local-model client          |

## Status

| Component                            | State                     |
|--------------------------------------|---------------------------|
| Brain 1 (Planner, deterministic)     | implemented               |
| Brain 2 (Critic, deterministic)      | implemented               |
| Brain 1 (Planner, LLM path)          | implemented + fallback    |
| Brain 2 (Critic, LLM path)           | implemented + fallback    |
| `MockLLMClient`                      | implemented               |
| `AnthropicClient`                    | implemented               |
| Orchestrator (single pass)           | implemented               |
| Memory (in-process + JSON)           | implemented               |
| CLI (run/show/history/clear/demo)    | implemented               |
| Iterative revise loop                | not yet                   |
| Execution agent                      | not yet                   |
| Other LLM providers (OpenAI, local)  | contract ready, not wired |
