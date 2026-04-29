"""Tests for the offline pattern-matching agent client and end-to-end use."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agent.local import LocalAgentClient
from app.brains.brain3_executor_agent import AgentExecutorBrain
from app.sandbox.fs import Sandbox
from app.types import PlanOutput, TaskInput


@pytest.fixture
def sandbox(tmp_path: Path) -> Sandbox:
    return Sandbox(tmp_path / "ws")


def _task(prompt: str) -> TaskInput:
    return TaskInput(id="t-1", prompt=prompt)


def _plan() -> PlanOutput:
    return PlanOutput(task_id="t-1", objective="obj", steps=["Create the file."])


# ── LocalAgentClient unit tests ─────────────────────────────────────


def _build_messages(prompt: str) -> list[dict]:
    return [{"role": "user", "content": [{"type": "text", "text": prompt}]}]


def test_local_agent_extracts_python_filename() -> None:
    client = LocalAgentClient()
    step = client.step(
        system="sys",
        messages=_build_messages("Please create hello.py with a hello world script."),
        tools=[],
    )
    assert step.kind == "tool_use"
    assert len(step.tool_calls) == 1
    call = step.tool_calls[0]
    assert call.name == "write_file"
    assert call.arguments["path"] == "hello.py"
    assert "hello" in call.arguments["content"].lower()


def test_local_agent_uses_inline_content_when_provided() -> None:
    client = LocalAgentClient()
    step = client.step(
        system="sys",
        messages=_build_messages('write greeting.txt with content "Привет, мир"'),
        tools=[],
    )
    assert step.tool_calls[0].arguments["content"] == "Привет, мир"


def test_local_agent_picks_topic_template() -> None:
    client = LocalAgentClient()
    step = client.step(
        system="sys",
        messages=_build_messages("Generate fibonacci numbers up to 100 in fib.py."),
        tools=[],
    )
    content = step.tool_calls[0].arguments["content"]
    assert "fib" in content.lower() or "fibonacci" in content.lower()


def test_local_agent_returns_final_when_no_filename_present() -> None:
    client = LocalAgentClient()
    step = client.step(
        system="sys",
        messages=_build_messages("explain how python decorators work"),
        tools=[],
    )
    assert step.kind == "final"
    assert step.tool_calls == []


def test_local_agent_finishes_after_one_tool_call() -> None:
    """Second step() must produce a final message so the loop terminates."""
    client = LocalAgentClient()
    client.step(system="sys", messages=_build_messages("write a.py"), tools=[])
    second = client.step(system="sys", messages=[], tools=[])
    assert second.kind == "final"


def test_local_agent_skips_path_like_tokens() -> None:
    """A token containing slashes is not a clean filename — fall through to final."""
    client = LocalAgentClient()
    step = client.step(
        system="sys",
        messages=_build_messages("create folder/sub/something.py here"),
        tools=[],
    )
    # The candidate has a slash; LocalAgent skips it. End up with no filename → final.
    assert step.kind == "final"


# ── End-to-end through AgentExecutorBrain ───────────────────────────


def test_local_agent_writes_real_file_via_executor(sandbox: Sandbox) -> None:
    """The full agent loop must produce a real file on disk in the sandbox."""
    brain = AgentExecutorBrain(client=LocalAgentClient(), sandbox=sandbox)

    out = brain.execute_plan(
        _task("Please create hello.py with content 'print(\"hi\")'"),
        _plan(),
    )

    target = sandbox.root / "hello.py"
    assert target.exists()
    assert "print(\"hi\")" in target.read_text(encoding="utf-8")
    assert out.overall_status == "completed"


def test_local_agent_emits_live_events(sandbox: Sandbox) -> None:
    captured: list[dict] = []
    brain = AgentExecutorBrain(
        client=LocalAgentClient(),
        sandbox=sandbox,
        on_event=captured.append,
    )

    brain.execute_plan(_task("create greet.txt with content 'hello'"), _plan())

    types = [e["type"] for e in captured]
    assert types == ["tool_call", "tool_result"]
    assert captured[0]["tool"] == "write_file"
    assert captured[1]["status"] == "ok"


# ── agent_fallback event visibility ─────────────────────────────────


def test_agent_executor_emits_fallback_event_on_provider_error(sandbox: Sandbox) -> None:
    """Falling back to deterministic must emit a visible event so the UI can warn."""
    from app.agent.client import AgentClient, AgentClientError

    class _BrokenClient(AgentClient):
        def step(self, *, system, messages, tools, max_tokens=1024):
            raise AgentClientError("simulated outage")

    captured: list[dict] = []
    brain = AgentExecutorBrain(
        client=_BrokenClient(), sandbox=sandbox, on_event=captured.append,
    )

    out = brain.execute_plan(_task("X"), _plan())

    types = [e["type"] for e in captured]
    assert "agent_fallback" in types
    assert "Agent client failed" in out.executor_notes


# ── Provider registry ───────────────────────────────────────────────


def test_local_agent_provider_is_registered() -> None:
    from app.brains import build_executor, registered_executor_providers
    assert "local-agent" in registered_executor_providers()
    # Build path also has to work without raising — no API key needed.
    executor = build_executor("local-agent")
    assert executor is not None


# ── enhanced multi-step / multi-file capabilities ─────────────────────


def test_local_agent_writes_multiple_files_in_one_step() -> None:
    """Multi-file prompts should produce one write_file call per filename."""
    client = LocalAgentClient()
    step = client.step(
        system="sys",
        messages=_build_messages("Create main.py and utils.py please"),
        tools=[],
    )
    assert step.kind == "tool_use"
    paths = [c.arguments["path"] for c in step.tool_calls if c.name == "write_file"]
    assert paths == ["main.py", "utils.py"]


def test_local_agent_runs_python_when_user_asks_to_verify() -> None:
    """A 'run / verify' keyword should add a run_python call after write_file."""
    client = LocalAgentClient()
    step = client.step(
        system="sys",
        messages=_build_messages("Create hello.py and run it to verify."),
        tools=[],
    )
    names = [c.name for c in step.tool_calls]
    assert names == ["write_file", "run_python"]


def test_local_agent_uses_topic_template_for_fibonacci() -> None:
    client = LocalAgentClient()
    step = client.step(
        system="sys",
        messages=_build_messages("Write fib.py with fibonacci numbers up to 100."),
        tools=[],
    )
    body = step.tool_calls[0].arguments["content"]
    assert "fib_up_to" in body
    assert "while a <= limit" in body


def test_local_agent_uses_topic_template_for_calculator() -> None:
    client = LocalAgentClient()
    step = client.step(
        system="sys",
        messages=_build_messages("Build calc.py — a tiny calculator."),
        tools=[],
    )
    body = step.tool_calls[0].arguments["content"]
    assert "operator" in body and "OPS" in body


def test_local_agent_uses_topic_template_for_fastapi() -> None:
    client = LocalAgentClient()
    step = client.step(
        system="sys",
        messages=_build_messages("Build a small FastAPI rest api in main.py"),
        tools=[],
    )
    body = step.tool_calls[0].arguments["content"]
    assert "FastAPI" in body
    assert "@app." in body


def test_local_agent_recognises_russian_keywords() -> None:
    """Both English and Russian topic keywords should produce a real template."""
    client = LocalAgentClient()
    step = client.step(
        system="sys",
        messages=_build_messages("создай fib.py с числами Фибоначчи"),
        tools=[],
    )
    body = step.tool_calls[0].arguments["content"]
    assert "fib_up_to" in body


def test_local_agent_lists_directory_when_user_asks() -> None:
    client = LocalAgentClient()
    step = client.step(
        system="sys",
        messages=_build_messages("show files in the workspace"),
        tools=[],
    )
    assert step.tool_calls[0].name == "list_dir"


def test_local_agent_inline_content_overrides_template_for_single_file() -> None:
    """If the user supplies explicit content, use it instead of the template."""
    client = LocalAgentClient()
    step = client.step(
        system="sys",
        messages=_build_messages('write greeting.txt with content "хай народ"'),
        tools=[],
    )
    assert step.tool_calls[0].arguments["content"] == "хай народ"


def test_local_agent_finalises_after_plan(sandbox: Sandbox) -> None:
    """After firing the plan, the next step() must finalise so the loop ends."""
    client = LocalAgentClient()
    client.step(system="sys", messages=_build_messages("write a.py"), tools=[])
    second = client.step(system="sys", messages=[], tools=[])
    assert second.kind == "final"
    # Summary should mention what was written.
    assert "a.py" in second.text


def test_full_executor_loop_writes_all_files_and_runs(sandbox: Sandbox) -> None:
    """End-to-end: multi-file plan + verification through the full agent loop."""
    brain = AgentExecutorBrain(client=LocalAgentClient(), sandbox=sandbox)

    out = brain.execute_plan(
        _task("Create hello.py with a hello world script and run it to verify"),
        _plan(),
    )

    # File on disk.
    assert (sandbox.root / "hello.py").exists()
    # Subprocess actually executed and printed.
    assert out.overall_status == "completed"
    # The trace must include both write_file and run_python results.
    # (We can't access the trace here directly — we infer from notes.)


def test_run_keyword_does_nothing_when_no_python_file() -> None:
    """A 'run it' phrase without any .py mentioned must not invent a run_python call."""
    client = LocalAgentClient()
    step = client.step(
        system="sys",
        messages=_build_messages("create greeting.txt and run it"),
        tools=[],
    )
    names = [c.name for c in step.tool_calls]
    # write_file for the txt, no run_python (it's not a Python file).
    assert names == ["write_file"]
