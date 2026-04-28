"""End-to-end tests for the autonomous executor (Brain 3).

Every test scripts the AgentClient with a list of canned ``AgentStep``
objects, so the loop runs offline and is byte-for-byte deterministic.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agent.client import AgentClient, AgentClientError, AgentStep, MockAgentClient
from app.brains.brain3_executor_agent import AgentExecutorBrain
from app.sandbox.fs import Sandbox
from app.types import PlanOutput, TaskInput, ToolCall


def _task() -> TaskInput:
    return TaskInput(id="t-1", prompt="Build a small thing.")


def _plan() -> PlanOutput:
    return PlanOutput(
        task_id="t-1",
        objective="obj",
        steps=["Create a file.", "Verify the file."],
        success_criteria=["File exists."],
    )


@pytest.fixture
def sandbox(tmp_path: Path) -> Sandbox:
    return Sandbox(tmp_path / "ws")


# ── happy path ───────────────────────────────────────────────────────


def test_agent_executor_writes_file_via_tool_call(sandbox: Sandbox) -> None:
    """The agent should be able to produce real artefacts inside the sandbox."""
    client = MockAgentClient(steps=[
        AgentStep(
            kind="tool_use",
            tool_calls=[ToolCall(name="write_file",
                                 arguments={"path": "out.txt", "content": "hello"})],
        ),
        AgentStep(kind="final", text="wrote out.txt"),
    ])

    brain = AgentExecutorBrain(client=client, sandbox=sandbox)
    out = brain.execute_plan(_task(), _plan())

    # Real file landed on disk.
    assert (sandbox.root / "out.txt").read_text(encoding="utf-8") == "hello"
    # ExecutionOutput is shaped the same as the deterministic executor's.
    assert out.task_id == "t-1"
    assert out.overall_status == "completed"
    assert all(r.status == "succeeded" for r in out.step_results)
    assert "out.txt" in out.executor_notes  # final text bubbled up


def test_agent_executor_emits_live_tool_events(sandbox: Sandbox) -> None:
    """on_event must fire once per tool_call AND once per tool_result."""
    client = MockAgentClient(steps=[
        AgentStep(
            kind="tool_use",
            tool_calls=[ToolCall(name="write_file",
                                 arguments={"path": "a.txt", "content": "hi"})],
        ),
        AgentStep(kind="final", text="ok"),
    ])
    captured: list[dict] = []
    brain = AgentExecutorBrain(
        client=client, sandbox=sandbox, on_event=captured.append,
    )

    brain.execute_plan(_task(), _plan())

    types = [e["type"] for e in captured]
    assert types == ["tool_call", "tool_result"]
    assert captured[0]["tool"] == "write_file"
    assert captured[1]["status"] == "ok"


# ── safety ───────────────────────────────────────────────────────────


def test_agent_executor_refuses_traversal_paths(sandbox: Sandbox) -> None:
    """The agent must NOT be able to write outside the sandbox, even if asked."""
    client = MockAgentClient(steps=[
        AgentStep(
            kind="tool_use",
            tool_calls=[ToolCall(name="write_file",
                                 arguments={"path": "../escape.txt", "content": "x"})],
        ),
        AgentStep(kind="final", text="tried but failed"),
    ])
    brain = AgentExecutorBrain(client=client, sandbox=sandbox)

    brain.execute_plan(_task(), _plan())

    # Nothing was written outside the sandbox.
    assert not (sandbox.root.parent / "escape.txt").exists()


def test_agent_executor_keeps_running_after_a_tool_error(sandbox: Sandbox) -> None:
    """A bad tool call must surface as an error to the model, not crash the loop."""
    client = MockAgentClient(steps=[
        AgentStep(
            kind="tool_use",
            tool_calls=[ToolCall(name="read_file", arguments={"path": "missing.txt"})],
        ),
        AgentStep(
            kind="tool_use",
            tool_calls=[ToolCall(name="write_file",
                                 arguments={"path": "ok.txt", "content": "ok"})],
        ),
        AgentStep(kind="final", text="recovered"),
    ])
    brain = AgentExecutorBrain(client=client, sandbox=sandbox)

    out = brain.execute_plan(_task(), _plan())

    assert (sandbox.root / "ok.txt").read_text(encoding="utf-8") == "ok"
    assert out.overall_status == "completed"


# ── halts and fallbacks ──────────────────────────────────────────────


def test_agent_executor_halts_on_max_iterations(sandbox: Sandbox) -> None:
    """A model that never returns 'final' must be cut off, not loop forever."""
    # Provide ten tool_use steps but only let the loop take 3.
    steps = [
        AgentStep(kind="tool_use",
                  tool_calls=[ToolCall(name="list_dir", arguments={})])
        for _ in range(10)
    ]
    client = MockAgentClient(steps=steps)
    brain = AgentExecutorBrain(client=client, sandbox=sandbox, max_iterations=3)

    out = brain.execute_plan(_task(), _plan())

    assert out.overall_status == "failed"
    assert "max_iterations" in out.executor_notes


def test_agent_executor_falls_back_on_provider_error(sandbox: Sandbox) -> None:
    """If the AgentClient raises, the deterministic executor takes over."""

    class _BrokenClient(AgentClient):
        def step(self, *, system, messages, tools, max_tokens=1024):
            raise AgentClientError("simulated outage")

    brain = AgentExecutorBrain(client=_BrokenClient(), sandbox=sandbox)

    out = brain.execute_plan(_task(), _plan())

    # Deterministic executor produces a non-empty step report and never crashes.
    assert out.task_id == "t-1"
    assert out.step_results
    assert "Deterministic executor" in out.executor_notes


# ── factory wiring ──────────────────────────────────────────────────


def test_agent_provider_is_registered_in_brain_factory() -> None:
    from app.brains import registered_executor_providers
    assert "agent" in registered_executor_providers()
