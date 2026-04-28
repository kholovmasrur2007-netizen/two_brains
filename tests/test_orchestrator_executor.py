"""Tests for the orchestrator's optional Brain 3 (Executor) integration."""

from __future__ import annotations

from app.brains import build_critic, build_planner
from app.brains.brain3_executor import ExecutorBrain
from app.core.orchestrator import TwoBrainOrchestrator
from app.types import ExecutionOutput, PlanOutput, TaskInput
from app.utils.helpers import new_id


class _SpyExecutor:
    """Records each execute_plan call and returns a canned report."""

    def __init__(self) -> None:
        self.calls: list[tuple[TaskInput, PlanOutput]] = []

    def execute_plan(self, task: TaskInput, plan: PlanOutput) -> ExecutionOutput:
        self.calls.append((task, plan))
        return ExecutionOutput(
            task_id=task.id,
            overall_status="completed",
            step_results=[],
            summary="spy",
            executor_notes="spy",
        )


def _ready_orchestrator(executor: object) -> TwoBrainOrchestrator:
    """A pipeline that always produces a ready_for_execution plan."""
    return TwoBrainOrchestrator(
        planner=build_planner("mock"),
        critic=build_critic("mock"),
        executor=executor,  # type: ignore[arg-type]
    )


def test_executor_not_invoked_by_default() -> None:
    """Without execute=True the orchestrator must not call Brain 3."""
    spy = _SpyExecutor()
    task = TaskInput(id=new_id(), prompt="Ship the next release.")

    result = _ready_orchestrator(spy).run(task)

    assert spy.calls == []
    assert result.execution is None


def test_executor_invoked_when_execute_true_and_ready() -> None:
    spy = _SpyExecutor()
    task = TaskInput(id=new_id(), prompt="Ship the next release.")

    result = _ready_orchestrator(spy).run(task, execute=True)

    assert len(spy.calls) == 1
    forwarded_task, forwarded_plan = spy.calls[0]
    assert forwarded_task.id == task.id
    assert forwarded_plan.task_id == task.id
    assert result.execution is not None
    assert result.execution.overall_status == "completed"
    assert result.execution.task_id == task.id


def test_executor_skipped_when_plan_not_ready() -> None:
    """An empty prompt fails the readiness bar — the executor must be skipped."""
    spy = _SpyExecutor()
    task = TaskInput(id=new_id(), prompt="")  # deterministic critique → not ready

    # Use the deterministic providers explicitly so the not-ready outcome is stable.
    orchestrator = TwoBrainOrchestrator(executor=spy)  # type: ignore[arg-type]
    result = orchestrator.run(task, execute=True)

    assert result.ready_for_execution is False
    assert spy.calls == []
    assert result.execution is None


def test_executor_result_persisted_in_memory() -> None:
    """The FinalResult stored in memory must include the execution artefact."""
    task = TaskInput(id=new_id(), prompt="Ship the next release.")
    orchestrator = _ready_orchestrator(ExecutorBrain())

    orchestrator.run(task, execute=True)

    stored = orchestrator.memory.get_result(task.id)
    assert stored is not None
    assert stored.execution is not None
    assert stored.execution.task_id == task.id
