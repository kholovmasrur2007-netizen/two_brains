"""Offline pattern-matching agent client.

A network-free ``AgentClient`` that:
    1. Extracts intent from the prompt — filename(s), topic, action verbs
       (run / verify / list / pytest).
    2. Looks up high-quality templates per (topic, extension) pair —
       fibonacci, primes, FastAPI, calculator, snake game, fizzbuzz, etc.
    3. Returns a multi-step ``AgentStep`` plan: write the file(s), then
       (if asked) ``run_python`` to verify, then a final summary.

It supports multi-file requests ("create main.py and utils.py") and
recognises both English and Russian keywords.

This is **not an LLM** — it's deterministic rules. It exists so the
autonomous executor produces real files, real subprocess output and
real tool-call streams without an Anthropic / OpenAI balance.
"""

from __future__ import annotations

from typing import Any

from app.agent.client import AgentClient, AgentStep
from app.agent.local_templates import (
    detect_topic,
    extract_filenames,
    extract_inline_content,
    render,
    wants_list,
    wants_pytest,
    wants_run,
)
from app.types import ToolCall


class LocalAgentClient(AgentClient):
    """A scripted, offline ``AgentClient`` that mimics multi-step agent behaviour.

    First call → returns a ``tool_use`` step with all derived tool calls
    in order (write_file × N, optional run_python, optional list_dir).
    Second call → returns a ``final`` step summarising what was done.
    Subsequent calls → idle ``final`` step (loop terminates).
    """

    def __init__(self) -> None:
        self._step_calls: int = 0
        self._fired_plan: bool = False
        self._summary: str = ""
        self.calls: list[dict[str, Any]] = []

    def step(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int = 1024,
    ) -> AgentStep:
        self._step_calls += 1
        self.calls.append({"system": system, "messages": list(messages)})

        if self._fired_plan:
            return AgentStep(
                kind="final",
                text=self._summary or "Local agent: done (offline mode).",
            )

        prompt = _first_user_text(messages)
        plan = self._derive_plan(prompt)
        if not plan:
            return AgentStep(
                kind="final",
                text=(
                    "Local agent: could not infer any tool calls from this prompt. "
                    "Try wording it like \"create hello.py\" or "
                    "\"write fib.py with fibonacci up to 100\". "
                    "Or top up the Anthropic / OpenAI balance and switch executor "
                    "to 'agent' / 'openai-agent' for full natural-language understanding."
                ),
            )

        self._fired_plan = True
        self._summary = _summarise_plan(plan)
        return AgentStep(kind="tool_use", tool_calls=plan)

    # ── prompt → tool plan ────────────────────────────────────────────

    @classmethod
    def _derive_plan(cls, prompt: str) -> list[ToolCall]:
        """Return the ordered tool calls the agent should make for ``prompt``."""
        filenames = extract_filenames(prompt)
        inline    = extract_inline_content(prompt)
        topic     = detect_topic(prompt)
        plan: list[ToolCall] = []

        # If the user only wants a directory listing, do that and stop.
        if not filenames and wants_list(prompt):
            plan.append(ToolCall(name="list_dir", arguments={"path": "."}))
            return plan

        # ── 1. Write each requested file ─────────────────────────────
        for name in filenames:
            ext = name.rsplit(".", 1)[-1].lower()
            content = inline if (inline and len(filenames) == 1) else render(topic, ext, prompt)
            plan.append(ToolCall(
                name="write_file",
                arguments={"path": name, "content": content},
            ))

        # ── 2. Optional: run the first .py file the user wants verified ──
        if wants_run(prompt):
            for name in filenames:
                if name.lower().endswith(".py"):
                    plan.append(ToolCall(name="run_python", arguments={"path": name}))
                    break

        # ── 3. Optional: pytest sweep ────────────────────────────────
        if wants_pytest(prompt):
            plan.append(ToolCall(name="run_pytest", arguments={"path": "."}))

        # ── 4. Optional: list workspace at the end ───────────────────
        if wants_list(prompt) and filenames:
            plan.append(ToolCall(name="list_dir", arguments={"path": "."}))

        return plan


# ── helpers ──────────────────────────────────────────────────────────


def _first_user_text(messages: list[dict[str, Any]]) -> str:
    """Pull the first user-role text out of a Claude-shaped message history."""
    for msg in messages:
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    return str(block.get("text", ""))
        if isinstance(content, str):
            return content
        return str(content)
    return ""


def _summarise_plan(plan: list[ToolCall]) -> str:
    """Human-readable summary of every tool call the agent issued."""
    if not plan:
        return "Local agent: no actions taken."

    parts: list[str] = []
    for call in plan:
        name = call.name
        args = call.arguments or {}
        if name == "write_file":
            parts.append(f"wrote {args.get('path', '?')}")
        elif name == "run_python":
            parts.append(f"ran {args.get('path', '?')}")
        elif name == "run_pytest":
            parts.append(f"ran pytest on {args.get('path', '.')}")
        elif name == "list_dir":
            parts.append("listed workspace")
        else:
            parts.append(name)
    return "Local agent: " + ", ".join(parts) + "."
