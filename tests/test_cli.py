"""Tests for the CLI dispatcher."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import app.config
import app.main as main_module
from app.main import build_parser


# ── shared fixture ────────────────────────────────────────────────────


@pytest.fixture
def isolated_memory(monkeypatch, tmp_path: Path) -> Path:
    """Point the CLI at a throw-away memory file for the duration of the test.

    Returns the Path so tests can inspect the JSON file afterwards.
    """
    path = tmp_path / "memory.json"

    class _Stub:
        memory_path = str(path)
        planner_provider = "deterministic"
        critic_provider = "deterministic"

    monkeypatch.setattr(app.config, "settings", _Stub())
    monkeypatch.setattr(main_module, "settings", _Stub())
    return path


# ── parser ─────────────────────────────────────────────────────────────


def test_parser_run_accepts_prompt_and_constraints() -> None:
    parser = build_parser()
    args = parser.parse_args(["run", "-c", "x", "-c", "y", "build", "a", "thing"])
    assert args.prompt == ["build", "a", "thing"]
    assert args.constraint == ["x", "y"]
    assert args.format == "text"
    assert args.func.__name__ == "cmd_run"


def test_parser_history_has_no_args() -> None:
    parser = build_parser()
    args = parser.parse_args(["history"])
    assert args.func.__name__ == "cmd_history"


def test_parser_show_requires_task_id() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["show"])  # missing task_id


def test_parser_clear_accepts_yes_flag() -> None:
    parser = build_parser()
    args = parser.parse_args(["clear", "--yes"])
    assert args.yes is True
    assert args.func.__name__ == "cmd_clear"


def test_parser_demo_is_registered() -> None:
    parser = build_parser()
    args = parser.parse_args(["demo"])
    assert args.func.__name__ == "cmd_demo"


# ── dispatch + exit codes ─────────────────────────────────────────────


def test_show_unknown_task_returns_error(isolated_memory, capsys) -> None:
    code = main_module.main(["show", "does-not-exist"])
    out = capsys.readouterr().out
    assert code == 2
    assert "no result" in out.lower()


def test_history_empty_returns_zero(isolated_memory, capsys) -> None:
    code = main_module.main(["history"])
    out = capsys.readouterr().out
    assert code == 0
    assert "no tasks" in out.lower()


def test_demo_runs_end_to_end_and_persists(isolated_memory, capsys) -> None:
    """`demo` should run without interactive input and produce a file."""
    code = main_module.main(["demo", "--format", "json"])
    assert code in (0, 1), "demo must exit with a defined pipeline code"
    # Demo prompt was written to disk — the file exists and is valid JSON.
    assert isolated_memory.exists()
    data = json.loads(isolated_memory.read_text(encoding="utf-8"))
    assert data["tasks"], "task must be persisted"
    assert data["results"], "result must be persisted"


def test_round_trip_run_then_show(isolated_memory, capsys) -> None:
    """A task stored by ``demo`` must be viewable via ``show <task_id>``."""
    main_module.main(["demo", "--format", "json"])
    data = json.loads(isolated_memory.read_text(encoding="utf-8"))
    task_id = next(iter(data["tasks"]))
    capsys.readouterr()  # clear buffer

    code = main_module.main(["show", task_id, "--format", "json"])
    out = capsys.readouterr().out

    assert code == 0, "show on a known task is always exit 0"
    assert task_id in out


def test_unknown_provider_surfaces_friendly_error(monkeypatch, capsys) -> None:
    """A bad planner provider should exit 2 with a clean message, no traceback."""
    class _Stub:
        memory_path = None
        planner_provider = "no-such-provider"
        critic_provider = "deterministic"
    monkeypatch.setattr(app.config, "settings", _Stub())
    monkeypatch.setattr(main_module, "settings", _Stub())

    code = main_module.main(["run", "Build something"])
    err = capsys.readouterr().err

    assert code == 2
    assert "no-such-provider" in err
