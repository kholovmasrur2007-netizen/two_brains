"""Offline pattern-matching agent client.

A small ``AgentClient`` that runs **without any API access**. It looks
at the user prompt, extracts a target filename plus inferred content,
and returns the matching ``write_file`` tool call as if a real model
had picked it. Useful for:

    * demoing the autonomous executor with no Anthropic balance
    * end-to-end smoke tests of the agent loop on real files
    * teaching the loop wiring to new contributors

It is intentionally tiny and naive — no LLM ambitions. If the prompt
doesn't match a known pattern, the client returns a final message
explaining what it would have needed.
"""

from __future__ import annotations

import re
from typing import Any

from app.agent.client import AgentClient, AgentStep
from app.types import ToolCall

# Match a likely filename: a short basename + a 1-5 char extension. We use
# look-arounds to avoid catching trailing punctuation (\"hello.py.\" → hello.py).
_FILENAME_RE = re.compile(r"(?<![\w/\\])([A-Za-z0-9_-]+\.[A-Za-z0-9]{1,5})(?![\w/\\])")

# Inline-content extractor. Handles patterns like:
#   create greeting.txt with content "hello world"
#   создай greeting.txt содержит 'print("hi")'
# We match the *opening* quote and use a non-greedy capture up to the
# matching *closing* quote of the same kind. That way a single-quoted
# content can contain double quotes (and vice versa) without the regex
# bailing out at the first inner quote.
_INLINE_CONTENT_RE = re.compile(
    r"(?:with\s+content|содержит|содержанием|текст(?:ом)?)\s+"
    r"(?P<q>[\"“«'])"        # opening quote (named so the backref reads cleanly)
    r"(?P<body>.+?)"          # content
    r"(?P=q)",                # same quote closes
    re.IGNORECASE | re.DOTALL,
)


class LocalAgentClient(AgentClient):
    """A pattern-matching, network-free ``AgentClient``.

    The first ``step()`` call inspects the initial user message, picks a
    target filename out of the prompt, and returns a ``write_file`` tool
    call with content inferred from the prompt's keywords. The second
    call returns a final summary so the agent loop terminates cleanly.

    If no usable filename can be extracted, the client returns a final
    message explaining what's missing — the agent loop still finishes,
    just with zero tool calls. This is far better than silently faking
    a "completed" status the deterministic executor would normally emit.
    """

    def __init__(self) -> None:
        self._step_calls: int = 0
        self._fired_tool: bool = False
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

        # Second + later turns: we already fired a tool call; finish.
        if self._fired_tool:
            return AgentStep(
                kind="final",
                text="Local agent: tool call complete. File written to the sandbox.",
            )

        prompt = _first_user_text(messages)
        filename = _extract_filename(prompt)
        if not filename:
            return AgentStep(
                kind="final",
                text=(
                    "Local agent: could not infer a target filename from the prompt. "
                    "Try wording it like \"create hello.py with content '...'\" "
                    "or top up the Anthropic balance and switch executor to 'agent'."
                ),
            )

        content = _infer_content(prompt, filename)
        self._fired_tool = True
        return AgentStep(
            kind="tool_use",
            tool_calls=[ToolCall(
                name="write_file",
                arguments={"path": filename, "content": content},
            )],
        )


# ── helpers ──────────────────────────────────────────────────────────


def _first_user_text(messages: list[dict[str, Any]]) -> str:
    """Pull the first user-role text out of a Claude-shaped messages list."""
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


def _extract_filename(prompt: str) -> str | None:
    """Return the first sandbox-safe filename mentioned in ``prompt``."""
    for match in _FILENAME_RE.finditer(prompt):
        candidate = match.group(1)
        # Skip anything that looks path-like — sandbox would reject it anyway.
        if "/" in candidate or "\\" in candidate or ".." in candidate:
            continue
        return candidate
    return None


def _infer_content(prompt: str, filename: str) -> str:
    """Best-effort content for the inferred file."""
    explicit = _INLINE_CONTENT_RE.search(prompt)
    if explicit:
        return explicit.group("body")

    low = prompt.lower()
    ext = filename.rsplit(".", 1)[-1].lower()

    # Topic-based templates that beat a generic "TODO: implement" stub.
    if "fibonacci" in low or "фибоначч" in low:
        if ext == "py":
            return _FIB_PY
    if "hello" in low or "привет" in low or "hello world" in low:
        if ext == "py":
            return _HELLO_PY
        if ext in ("html", "htm"):
            return _HELLO_HTML
        if ext in ("txt", "md"):
            return "Hello, world!\n"
    if "calculator" in low or "калькулят" in low:
        if ext == "py":
            return _CALC_PY

    # Generic fallback — non-empty, syntactically valid for common extensions.
    return _GENERIC.get(ext, f"# Auto-generated by LocalAgent for: {prompt[:80]}\n")


_HELLO_PY = (
    '"""Hello-world script generated by the offline LocalAgent."""\n\n'
    'def main() -> None:\n'
    '    print("Hello, world!")\n\n\n'
    'if __name__ == "__main__":\n'
    '    main()\n'
)

_HELLO_HTML = (
    "<!doctype html>\n"
    "<html><head><meta charset='utf-8'><title>Hello</title></head>\n"
    "<body><h1>Hello, world!</h1></body></html>\n"
)

_FIB_PY = (
    '"""Fibonacci numbers up to a limit, generated by the offline LocalAgent."""\n\n'
    'def fib_up_to(limit: int) -> list[int]:\n'
    '    out: list[int] = []\n'
    '    a, b = 0, 1\n'
    '    while a <= limit:\n'
    '        out.append(a)\n'
    '        a, b = b, a + b\n'
    '    return out\n\n\n'
    'if __name__ == "__main__":\n'
    '    print(fib_up_to(100))\n'
)

_CALC_PY = (
    '"""Tiny calculator, generated by the offline LocalAgent."""\n\n'
    'import operator\n\n'
    'OPS = {"+": operator.add, "-": operator.sub, "*": operator.mul, "/": operator.truediv}\n\n'
    'def calc(expr: str) -> float:\n'
    '    a, op, b = expr.split()\n'
    '    return OPS[op](float(a), float(b))\n\n\n'
    'if __name__ == "__main__":\n'
    '    print(calc("2 + 2"))\n'
)

_GENERIC: dict[str, str] = {
    "py":   '"""Auto-generated by LocalAgent."""\n\n# TODO: implement\n',
    "txt":  "Generated by LocalAgent.\n",
    "md":   "# Generated by LocalAgent\n\nTODO: write content.\n",
    "json": "{}\n",
    "html": "<!doctype html>\n<html><body>Generated by LocalAgent</body></html>\n",
    "css":  "/* Generated by LocalAgent */\n",
    "js":   "// Generated by LocalAgent\n",
}
