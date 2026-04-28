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
