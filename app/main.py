"""CLI entry point for the two_brains pipeline.

Usage examples:

    # interactive - prompts for the task
    python -m app.main

    # one-shot - prompt passed as argument
    python -m app.main "Build a calculator web app."

    # with constraints
    python -m app.main -c "single-file HTML" -c "no backend" "Build a calculator."

    # read task from stdin
    echo "Plan a weekend trip" | python -m app.main

    # JSON output (for pipes, scripts, CI)
    python -m app.main --format json "Build X."

    # run a pre-baked demo task
    python -m app.main demo

    # replay a past run
    python -m app.main show <task_id>

    # list what's in memory
    python -m app.main history

    # clear the memory file
    python -m app.main clear --yes

Exit codes:
    0    pipeline ran, plan is ready_for_execution (or command succeeded)
    1    pipeline ran, plan needs revision
    2    error (invalid input, missing task, disk failure, ...)
    130  interrupted with Ctrl+C
"""

from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path
from typing import Sequence

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from app.config import settings
from app.core.orchestrator import TwoBrainOrchestrator
from app.memory.store import MemoryStore
from app.types import CritiqueOutput, ExecutionOutput, FinalResult, PlanOutput, TaskInput
from app.utils.helpers import new_id

EXIT_OK: int = 0
EXIT_REVISION_NEEDED: int = 1
EXIT_ERROR: int = 2
EXIT_INTERRUPTED: int = 130

_JUDGEMENT_COLOUR: dict[str, str] = {
    "accepted":              "green",
    "needs_minor_revision":  "yellow",
    "needs_major_revision":  "red",
    "rejected":              "red",
    "pending":               "white",
}

_STEP_STATUS_COLOUR: dict[str, str] = {
    "succeeded": "green",
    "failed":    "red",
    "skipped":   "yellow",
}

_OVERALL_STATUS_COLOUR: dict[str, str] = {
    "completed": "green",
    "partial":   "yellow",
    "failed":    "red",
    "not_run":   "dim",
}

_KNOWN_SUBCOMMANDS: frozenset[str] = frozenset(
    {"run", "show", "history", "clear", "demo", "agent"}
)

# Small, predictable demo task so ``python -m app.main demo`` never requires input.
DEMO_PROMPT: str = "Migrate the users table to a new schema in production."
DEMO_CONSTRAINTS: list[str] = ["zero downtime", "rollback required"]


# ── rendering ─────────────────────────────────────────────────────────


def _render_task(task: TaskInput, console: Console) -> None:
    body = Text()
    body.append("prompt:      ", style="bold")
    body.append(task.prompt + "\n")
    if task.constraints:
        body.append("constraints: ", style="bold")
        body.append(", ".join(task.constraints) + "\n")
    body.append("id:          ", style="bold dim")
    body.append(task.id, style="dim")
    console.print(Panel(body, title="Task", border_style="cyan", title_align="left"))


def _render_plan(plan: PlanOutput, console: Console) -> None:
    table = Table(title="Plan", title_style="bold magenta", show_header=True, header_style="bold")
    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("Step")
    for i, step in enumerate(plan.steps, start=1):
        table.add_row(str(i), step)
    console.print(table)

    meta = Table(show_header=False, box=None, padding=(0, 1))
    meta.add_column(style="bold", min_width=18)
    meta.add_column()
    meta.add_row("Objective:", plan.objective or "[dim](none)[/dim]")
    if plan.assumptions:
        meta.add_row("Assumptions:", "\n".join(f"- {a}" for a in plan.assumptions))
    if plan.constraints:
        meta.add_row("Constraints:", ", ".join(plan.constraints))
    if plan.risks:
        meta.add_row("Risks:", "\n".join(f"- {r}" for r in plan.risks))
    if plan.success_criteria:
        meta.add_row("Success criteria:", "\n".join(f"- {c}" for c in plan.success_criteria))
    console.print(meta)


def _render_critique(critique: CritiqueOutput, console: Console) -> None:
    colour = _JUDGEMENT_COLOUR.get(critique.final_judgement, "white")
    console.print(
        f"\n[bold]Score:[/bold] {critique.overall_score}/100    "
        f"[bold]Judgement:[/bold] [{colour}]{critique.final_judgement}[/{colour}]"
    )
    sections: list[tuple[str, str, list[str], str]] = [
        ("green",  "Strengths",        critique.strengths,               "[+]"),
        ("yellow", "Weaknesses",       critique.weaknesses,              "[-]"),
        ("red",    "Missing",          critique.missing_elements,        "[!]"),
        ("red",    "Contradictions",   critique.contradictions,          "[X]"),
        ("red",    "Risk flags",       critique.risk_flags,              "[R]"),
        ("cyan",   "Suggestions",      critique.improvement_suggestions, "[>]"),
        ("dim",    "Per-step notes",   critique.revised_step_notes,      "[.]"),
    ]
    for section_colour, title, items, bullet in sections:
        if not items:
            continue
        console.print(f"\n[{section_colour}]{title}:[/{section_colour}]")
        for item in items:
            console.print(f"  {bullet} {item}")


def _render_recommendation(result: FinalResult, console: Console) -> None:
    colour = "green" if result.ready_for_execution else "yellow"
    body = Text()
    body.append("ready_for_execution: ", style="bold")
    body.append(str(result.ready_for_execution) + "\n", style=colour)
    body.append("recommendation:      ", style="bold")
    body.append(result.final_recommendation)
    console.print(Panel(body, title="Final recommendation", border_style=colour, title_align="left"))


def _render_execution(execution: ExecutionOutput, console: Console) -> None:
    overall_colour = _OVERALL_STATUS_COLOUR.get(execution.overall_status, "white")
    table = Table(
        title="Execution",
        title_style="bold magenta",
        show_header=True,
        header_style="bold",
    )
    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("Step")
    table.add_column("Status", width=10)
    table.add_column("Output / error")
    for r in execution.step_results:
        status_colour = _STEP_STATUS_COLOUR.get(r.status, "white")
        detail = r.error if r.status == "failed" and r.error else r.output
        table.add_row(
            str(r.index),
            r.step,
            f"[{status_colour}]{r.status}[/{status_colour}]",
            detail,
        )
    console.print(table)
    console.print(
        f"\n[bold]Overall:[/bold] [{overall_colour}]{execution.overall_status}[/{overall_colour}]    "
        f"{execution.summary}"
    )
    if execution.executor_notes:
        console.print(f"[dim]{execution.executor_notes}[/dim]")


def _render_final(result: FinalResult, console: Console) -> None:
    """Render the sections the user cares about: task, plan, critique, recommendation, (execution)."""
    _render_task(result.original_task, console)
    _render_plan(result.plan, console)
    _render_critique(result.critique, console)
    _render_recommendation(result, console)
    if result.execution is not None:
        _render_execution(result.execution, console)


# ── helpers ───────────────────────────────────────────────────────────


def _emit(result: FinalResult, fmt: str, console: Console) -> None:
    """Output a FinalResult in the requested format."""
    if fmt == "json":
        print(result.model_dump_json(indent=2))
    else:
        _render_final(result, console)


class _Cancelled(Exception):
    """Raised when the user aborts an interactive prompt."""


def _resolve_prompt(args: argparse.Namespace) -> str:
    """Resolve the task prompt from argv, stdin, or an interactive prompt.

    Returns:
        The prompt as a non-empty string.

    Raises:
        _Cancelled: user aborted the interactive prompt (Ctrl+C / EOF).
        ValueError: no prompt could be resolved (empty argv/stdin).
    """
    prompt = " ".join(args.prompt).strip() if args.prompt else ""
    if prompt:
        return prompt
    if not sys.stdin.isatty():
        piped = sys.stdin.read().strip()
        if piped:
            return piped
        raise ValueError("stdin produced an empty prompt")
    try:
        typed = Prompt.ask("[bold cyan]task[/bold cyan]").strip()
    except (EOFError, KeyboardInterrupt) as e:
        raise _Cancelled from e
    if not typed:
        raise ValueError("no prompt provided")
    return typed


# ── commands ──────────────────────────────────────────────────────────


def _run_task(
    task: TaskInput,
    fmt: str,
    debug: bool,
    console: Console,
    execute: bool = False,
) -> int:
    """Shared pipeline runner used by both ``cmd_run`` and ``cmd_demo``."""
    orchestrator = TwoBrainOrchestrator(memory=MemoryStore(path=settings.memory_path))
    try:
        result = orchestrator.run(task, execute=execute)
    except Exception as e:
        console.print(f"[red]pipeline error:[/red] {e.__class__.__name__}: {e}")
        if debug:
            console.print_exception()
        return EXIT_ERROR
    _emit(result, fmt, console)
    return EXIT_OK if result.ready_for_execution else EXIT_REVISION_NEEDED


def cmd_run(args: argparse.Namespace) -> int:
    """Run a task through the pipeline and print the result."""
    console = Console()
    try:
        prompt = _resolve_prompt(args)
    except _Cancelled:
        console.print("cancelled")
        return EXIT_INTERRUPTED
    except ValueError as e:
        console.print(f"[red]error:[/red] {e}")
        return EXIT_ERROR

    task = TaskInput(
        id=new_id(),
        prompt=prompt,
        constraints=list(args.constraint or []),
    )
    return _run_task(task, args.format, args.debug, console, execute=args.execute)


def cmd_demo(args: argparse.Namespace) -> int:
    """Run a small pre-baked demo task so the pipeline can be tried without input."""
    console = Console()
    console.print(
        "[dim]demo task:[/dim] "
        f"[bold]{DEMO_PROMPT}[/bold] "
        f"[dim]{DEMO_CONSTRAINTS}[/dim]\n"
    )
    task = TaskInput(id=new_id(), prompt=DEMO_PROMPT, constraints=list(DEMO_CONSTRAINTS))
    return _run_task(task, args.format, args.debug, console, execute=args.execute)


def cmd_agent(args: argparse.Namespace) -> int:
    """Run a task end-to-end with the autonomous agent executor.

    Equivalent to ``run --execute`` with ``EXECUTOR_PROVIDER=agent`` forced
    on for this single invocation. The agent is confined to the sandbox
    workspace configured in ``settings.agent_workspace``; absolute paths
    and traversal segments are rejected before any I/O. Provider-side
    failures (no API key, network outage) fall back to the deterministic
    executor so the command still terminates with a usable result.
    """
    from app.brains import build_critic, build_executor, build_planner

    console = Console()
    try:
        prompt = _resolve_prompt(args)
    except _Cancelled:
        console.print("cancelled")
        return EXIT_INTERRUPTED
    except ValueError as e:
        console.print(f"[red]error:[/red] {e}")
        return EXIT_ERROR

    task = TaskInput(
        id=new_id(),
        prompt=prompt,
        constraints=list(args.constraint or []),
    )

    try:
        executor = build_executor("agent")
    except Exception as e:  # noqa: BLE001 - missing key, etc.
        console.print(f"[red]agent unavailable:[/red] {e}")
        if args.debug:
            console.print_exception()
        return EXIT_ERROR

    orchestrator = TwoBrainOrchestrator(
        planner=build_planner(settings.planner_provider),
        critic=build_critic(settings.critic_provider),
        executor=executor,
        memory=MemoryStore(path=settings.memory_path),
    )

    def on_event(event: dict) -> None:
        et = event.get("type")
        if et == "tool_call":
            console.print(
                f"[cyan]→ {event['tool']}[/cyan] "
                f"[dim]iter {event.get('iteration')} {event.get('arguments')}[/dim]"
            )
        elif et == "tool_result":
            colour = "green" if event.get("status") == "ok" else "red"
            detail = event.get("output") or event.get("error") or ""
            console.print(
                f"  [{colour}]{event.get('status')}[/{colour}] "
                f"[dim]{detail[:120]}[/dim]"
            )

    try:
        result = orchestrator.run(task, execute=True, on_event=on_event)
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]pipeline error:[/red] {e.__class__.__name__}: {e}")
        if args.debug:
            console.print_exception()
        return EXIT_ERROR

    _emit(result, args.format, console)
    return EXIT_OK if result.ready_for_execution else EXIT_REVISION_NEEDED


def cmd_show(args: argparse.Namespace) -> int:
    """Print a previously saved FinalResult by its task_id.

    ``show`` is a read command, so exit 0 on success regardless of whether
    the plan was marked ready. Only missing task ids become exit 2.
    """
    console = Console()
    memory = MemoryStore(path=settings.memory_path)
    result = memory.get_result(args.task_id)
    if result is None:
        console.print(
            f"[red]error:[/red] no result stored for task_id=[bold]{args.task_id}[/bold]"
        )
        return EXIT_ERROR
    _emit(result, args.format, console)
    return EXIT_OK


def cmd_history(args: argparse.Namespace) -> int:
    """List every task currently in memory."""
    console = Console()
    memory = MemoryStore(path=settings.memory_path)
    task_ids = memory.known_task_ids()
    if not task_ids:
        console.print("[dim]no tasks in memory[/dim]")
        return EXIT_OK

    table = Table(
        title="Task history",
        title_style="bold cyan",
        show_header=True,
        header_style="bold",
    )
    table.add_column("Task ID", style="cyan")
    table.add_column("Prompt")
    table.add_column("Score", justify="right")
    table.add_column("Judgement")
    table.add_column("Ready", justify="center")

    for tid in task_ids:
        task = memory.get_task(tid)
        critique = memory.get_critique(tid)
        result = memory.get_result(tid)
        prompt = textwrap.shorten(task.prompt, width=60, placeholder="...") if task else ""
        score = str(critique.overall_score) if critique else "-"
        judgement_raw = critique.final_judgement if critique else "-"
        judgement = f"[{_JUDGEMENT_COLOUR.get(judgement_raw, 'white')}]{judgement_raw}[/]"
        if result is None:
            ready = "-"
        elif result.ready_for_execution:
            ready = "[green]YES[/green]"
        else:
            ready = "[yellow]no[/yellow]"
        table.add_row(tid, prompt, score, judgement, ready)
    console.print(table)
    return EXIT_OK


def cmd_clear(args: argparse.Namespace) -> int:
    """Delete the JSON memory file."""
    console = Console()
    if not settings.memory_path:
        console.print("[dim]no memory file configured (MEMORY_PATH is unset)[/dim]")
        return EXIT_OK
    path = Path(settings.memory_path)
    if not path.exists():
        console.print("[dim]memory file does not exist[/dim]")
        return EXIT_OK
    if not args.yes:
        try:
            response = Prompt.ask(
                f"delete [bold]{path}[/bold]?", choices=["y", "n"], default="n"
            )
        except (EOFError, KeyboardInterrupt):
            console.print()
            return EXIT_ERROR
        if response != "y":
            console.print("aborted")
            return EXIT_OK
    try:
        path.unlink()
    except OSError as e:
        console.print(f"[red]error:[/red] could not delete {path}: {e}")
        return EXIT_ERROR
    console.print(f"removed [bold]{path}[/bold]")
    return EXIT_OK


# ── argparse wiring ───────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser with its subcommands."""
    parser = argparse.ArgumentParser(
        prog="two_brains",
        description="Run a TaskInput through the Planner -> Critic pipeline.",
    )
    sub = parser.add_subparsers(dest="command")

    p_run = sub.add_parser("run", help="Run a task through the pipeline (default).")
    p_run.add_argument("prompt", nargs="*", help="Task prompt (or read from stdin/prompt).")
    p_run.add_argument("-c", "--constraint", action="append",
                       help="Add a constraint; repeatable.")
    p_run.add_argument("--format", choices=["text", "json"], default="text",
                       help="Output format.")
    p_run.add_argument("--execute", action="store_true",
                       help="Run Brain 3 (Executor) on the finalised plan when ready.")
    p_run.add_argument("--debug", action="store_true",
                       help="Show full traceback on pipeline errors.")
    p_run.set_defaults(func=cmd_run)

    p_show = sub.add_parser("show", help="Print the saved result for a task_id.")
    p_show.add_argument("task_id")
    p_show.add_argument("--format", choices=["text", "json"], default="text")
    p_show.set_defaults(func=cmd_show)

    p_hist = sub.add_parser("history", help="List every task in memory.")
    p_hist.set_defaults(func=cmd_history)

    p_clr = sub.add_parser("clear", help="Delete the JSON memory file.")
    p_clr.add_argument("--yes", action="store_true",
                       help="Skip the confirmation prompt.")
    p_clr.set_defaults(func=cmd_clear)

    p_demo = sub.add_parser("demo", help="Run a small pre-baked demo task.")
    p_demo.add_argument("--format", choices=["text", "json"], default="text")
    p_demo.add_argument("--execute", action="store_true",
                        help="Run Brain 3 (Executor) on the finalised plan when ready.")
    p_demo.add_argument("--debug", action="store_true",
                        help="Show full traceback on pipeline errors.")
    p_demo.set_defaults(func=cmd_demo)

    p_ag = sub.add_parser(
        "agent",
        help="Autonomous mode: plan + critique + execute the task with sandboxed file tools.",
    )
    p_ag.add_argument("prompt", nargs="*", help="Task prompt (or read from stdin/prompt).")
    p_ag.add_argument("-c", "--constraint", action="append", help="Add a constraint; repeatable.")
    p_ag.add_argument("--format", choices=["text", "json"], default="text")
    p_ag.add_argument("--debug", action="store_true",
                      help="Show full traceback on pipeline errors.")
    p_ag.set_defaults(func=cmd_agent)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and dispatch. Usable from both __main__ and tests."""
    parser = build_parser()
    raw = list(argv) if argv is not None else sys.argv[1:]

    # Friendly default: if the first arg is not a known subcommand, treat the
    # whole argument vector as implicit `run <prompt>`. This lets the user type
    # ``python -m app.main "Build X"`` without having to write ``run``.
    if not raw or (raw[0] not in _KNOWN_SUBCOMMANDS and raw[0] not in ("-h", "--help")):
        raw = ["run"] + raw

    args = parser.parse_args(raw)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return EXIT_INTERRUPTED
    except Exception as e:
        # Last-resort guard so the CLI never surfaces a raw traceback.
        sys.stderr.write(f"error: {e.__class__.__name__}: {e}\n")
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
