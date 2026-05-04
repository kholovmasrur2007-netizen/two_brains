"""Telegram-bot front-end for two_brains.

Bridges Telegram chat ↔ the two_brains REST API.

Commands:
    /start    welcome message + tutorial
    /run      run a task: ``/run write hello.py with hello world``
    /status   liveness probe of the upstream service
    /usage    today's quota usage for the bot's service account
    /help     short reminder of every command

Environment:
    TELEGRAM_BOT_TOKEN   token from @BotFather (required)
    TWOBRAINS_URL        base URL of the two_brains API (default http://app:8000
                         when running inside docker-compose; http://localhost:8000
                         for local dev)
    TWOBRAINS_USERNAME   service account login (default: bot)
    TWOBRAINS_PASSWORD   service account password (default: bot)

The bot logs in once at start, caches the JWT token, and re-logs in
when the token is rejected. All errors are surfaced to the chat — never
swallowed silently.
"""

from __future__ import annotations

import logging
import os
import re
import textwrap
import time

import httpx
from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("two_brains.telegram")

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
API_BASE = os.environ.get("TWOBRAINS_URL", "http://app:8000").rstrip("/")
SERVICE_USER = os.environ.get("TWOBRAINS_USERNAME", "bot")
SERVICE_PASS = os.environ.get("TWOBRAINS_PASSWORD", "bot")

# ── Admin (free LLM chat) configuration ──────────────────────────────
# /admin <password> unlocks free-form LLM chat for the calling chat.
# The provider is selected via ADMIN_PROVIDER:
#   "ollama"    — local model via http://localhost:11434 (default; free, offline)
#   "anthropic" — Claude API (needs ANTHROPIC_API_KEY + paid balance)
ADMIN_PASSWORD     = os.environ.get("ADMIN_PASSWORD", "")
ADMIN_PROVIDER     = os.environ.get("ADMIN_PROVIDER", "ollama").lower()
ADMIN_MODEL        = os.environ.get("ADMIN_MODEL", "qwen2.5:7b")
ANTHROPIC_API_KEY  = os.environ.get("ANTHROPIC_API_KEY", "")
OLLAMA_URL         = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")

_admin_chats: set[int] = set()
_chat_history: dict[int, list[dict]] = {}   # chat_id -> [{role, content}]
_HISTORY_MAX = 20                            # turns per chat

_SYSTEM_PROMPT = (
    "Ты — личный AI-ассистент. Отвечай по-русски, на ты, кратко и по существу. "
    "Без воды, без вступлений типа «отличный вопрос», без перечисления того что собираешься сказать. "
    "Сразу ответ. Если вопрос требует кода — сразу код в блоке ```python ... ```. "
    "Если вопрос факт — короткий ответ в 1-3 предложениях. "
    "Если не знаешь — честно скажи «не знаю». Не выдумывай ссылки и цифры. "
    "Не используй ## заголовки и markdown-разметку (Telegram её не рендерит). "
    "Длина ответа — обычно 50-200 слов; больше только если задача требует."
)

_anthropic_client = None
def _anthropic():
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic
        _anthropic_client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    return _anthropic_client

# Reuse one HTTP client across requests for connection pooling.
_http: httpx.AsyncClient | None = None
_jwt: str | None = None


# ── auth + http plumbing ─────────────────────────────────────────────


async def _client() -> httpx.AsyncClient:
    global _http
    if _http is None:
        _http = httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=10.0))
    return _http


async def _ensure_token() -> str | None:
    """Return a valid JWT, logging in (or creating the user) when needed."""
    global _jwt
    if _jwt:
        return _jwt
    cli = await _client()
    try:
        r = await cli.post(
            f"{API_BASE}/auth/login",
            json={"username": SERVICE_USER, "password": SERVICE_PASS},
        )
        if r.status_code == 200:
            _jwt = r.json().get("access_token")
            log.info("logged in as %s", SERVICE_USER)
            return _jwt
        log.warning("login %s failed (%s) — auth probably disabled", SERVICE_USER, r.status_code)
    except httpx.RequestError as e:
        log.warning("auth request failed: %s — assuming auth disabled", e)
    return None  # auth disabled — call without token


def _auth_headers(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token else {}


# ── handlers ─────────────────────────────────────────────────────────


WELCOME = textwrap.dedent("""\
    👋 two_brains v3.0 — самый безопасный AI-агент.

    Я умею:
      /run [задача]   — поставить задачу агенту
      /status         — проверить, жив ли сервис
      /usage          — посмотреть остаток дневной квоты
      /help           — справка

    Пример:
      /run create hello.py with a hello world script and run it to verify

    Я говорю с локальным two_brains API. Безопасно, без shell, в песочнице.
""")

HELP = textwrap.dedent("""\
    Команды:
      /run [prompt]  — запустить задачу через двухмозговой пайплайн
      /status        — проверить /health upstream-сервиса
      /usage         — сколько задач осталось сегодня по квоте
      /start         — приветствие
      /help          — эта справка

    Принципы:
    • двойной критик блокирует rm -rf, sudo, traversal
    • план не запускается, если score < 85
    • файлы пишутся только в твою песочницу
""")


async def cmd_start(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    # No parse_mode — keeps the message reliable across Markdown special chars.
    await update.effective_message.reply_text(WELCOME)


async def cmd_help(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(HELP)


async def cmd_status(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    cli = await _client()
    try:
        r = await cli.get(f"{API_BASE}/health")
        data = r.json()
        await update.effective_message.reply_text(
            f"✅ upstream: ok\nuptime: {data.get('uptime_seconds', '?')}s"
        )
    except Exception as e:  # noqa: BLE001
        await update.effective_message.reply_text(f"❌ upstream недоступен: {e}")


async def cmd_usage(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    token = await _ensure_token()
    cli = await _client()
    try:
        r = await cli.get(f"{API_BASE}/api/usage", headers=_auth_headers(token))
        if r.status_code != 200:
            await update.effective_message.reply_text(f"⚠ {r.status_code} {r.text[:200]}")
            return
        u = r.json()
        await update.effective_message.reply_text(
            f"📊 Квота\n"
            f"Использовано сегодня: {u['used_today']}\n"
            f"Дневной лимит:        {u['daily_quota']}\n"
            f"Осталось:              {u['remaining']}"
        )
    except Exception as e:  # noqa: BLE001
        await update.effective_message.reply_text(f"❌ {e}")


_FILENAME_IN_OUTPUT = re.compile(r"\bwrote\s+\d+\s+chars\s+to\s+(\S+)")
_RUN_OUTPUT_LINE    = re.compile(r"^exit_code=0\s*\n(.*)", re.MULTILINE | re.DOTALL)


async def cmd_run(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/run [task]  — invoked explicitly."""
    msg = update.effective_message
    prompt = " ".join(ctx.args).strip() if ctx.args else ""
    if not prompt:
        await msg.reply_text(
            "📝 Просто напиши задачу — без /run.\n"
            "Например: «сделай hello.py с приветом»"
        )
        return
    await _handle_task(msg, prompt)


async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/admin <password> — unlock free LLM chat for this Telegram chat."""
    msg = update.effective_message
    chat_id = update.effective_chat.id
    if not ADMIN_PASSWORD:
        await msg.reply_text(
            "⚠ Админ-режим не настроен. Задай ADMIN_PASSWORD в .env и перезапусти бота."
        )
        return
    pwd = " ".join(ctx.args).strip() if ctx.args else ""
    if pwd == ADMIN_PASSWORD:
        _admin_chats.add(chat_id)
        _chat_history[chat_id] = []
        await msg.reply_text(
            "👋 Доступ подтверждён, генерал.\n"
            "Теперь я отвечаю на любой твой вопрос (свободный чат с Claude).\n\n"
            "Напиши что-нибудь — например «расскажи как работает Python» или "
            "«дай 5 идей для стартапа».\n\n"
            "/forget — очистить историю беседы\n"
            "/exit_admin — выйти из админ-режима"
        )
    else:
        await msg.reply_text("❌ Неверный код.")


async def cmd_forget(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/forget — clear conversation history."""
    chat_id = update.effective_chat.id
    _chat_history[chat_id] = []
    await update.effective_message.reply_text("🧹 История беседы очищена.")


async def cmd_exit_admin(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/exit_admin — leave free-chat mode, go back to agent task mode."""
    chat_id = update.effective_chat.id
    _admin_chats.discard(chat_id)
    _chat_history.pop(chat_id, None)
    await update.effective_message.reply_text(
        "👋 Вышел из админ-режима. Снова работаю как агент."
    )


async def on_plain_text(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Любой текст без слеша.

    Админ-чат → свободный диалог через Anthropic.
    Иначе → задача агенту two_brains.
    """
    msg = update.effective_message
    chat_id = update.effective_chat.id
    text = (msg.text or "").strip()
    if not text:
        return

    if chat_id in _admin_chats:
        await _handle_admin_chat(msg, chat_id, text)
    else:
        await _handle_task(msg, text)


async def _handle_admin_chat(msg, chat_id: int, user_text: str) -> None:
    """Free-form LLM chat with per-chat conversation history.

    Routes to Ollama (local, free, streamed) or Anthropic (cloud, paid)
    depending on ADMIN_PROVIDER. Streaming makes the bot feel responsive
    even when the underlying CPU inference is slow — text appears word by
    word via edit_message_text instead of arriving as one giant blob.
    """
    history = _chat_history.setdefault(chat_id, [])
    history = history[-(_HISTORY_MAX * 2):]
    history.append({"role": "user", "content": user_text})

    await msg.chat.send_action(action=ChatAction.TYPING)

    try:
        if ADMIN_PROVIDER == "ollama":
            answer = await _ollama_reply_streamed(history, msg)
        elif ADMIN_PROVIDER == "anthropic":
            answer = await _anthropic_reply(history)
            for chunk in _chunks(answer, 3500):
                await msg.reply_text(chunk)
        else:
            await msg.reply_text(
                f"⚠ Неизвестный ADMIN_PROVIDER='{ADMIN_PROVIDER}'. "
                "Допустимо: 'ollama' или 'anthropic'."
            )
            return
    except Exception as e:  # noqa: BLE001
        if history and history[-1].get("role") == "user":
            history.pop()
        await msg.reply_text(f"❌ {ADMIN_PROVIDER}: {e.__class__.__name__}: {str(e)[:400]}")
        return

    answer = (answer or "").strip() or "(пустой ответ)"
    history.append({"role": "assistant", "content": answer})
    _chat_history[chat_id] = history


async def _anthropic_reply(history: list[dict]) -> str:
    """Send the conversation to Anthropic Messages API and return the text."""
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY не задан")
    response = await _anthropic().messages.create(
        model=ADMIN_MODEL,
        system=_SYSTEM_PROMPT,
        messages=history,
        max_tokens=2048,
    )
    return "".join(
        getattr(b, "text", "") for b in response.content
        if getattr(b, "type", None) == "text"
    )


async def _ollama_reply_streamed(history: list[dict], msg) -> str:
    """Stream Ollama tokens into a single Telegram message via edit_message_text.

    User experience:
      • Within ~5 seconds, an empty placeholder message appears.
      • As Ollama produces tokens, the message text grows via
        edit_message_text. Telegram rate-limits edits to ~5/s per chat,
        so we batch updates every 1.5 seconds and skip if the text
        didn't change since the last edit.
      • When generation finishes, the final full text is committed
        and returned.

    Tuned for CPU-only machines:
      * ``keep_alive: -1`` — model stays resident between requests
        (no 5 GB reload from disk).
      * ``num_predict: 400`` — caps reply length so the model doesn't
        ramble for minutes when each token costs a second.
      * ``num_ctx: 4096`` — fits normal chat but keeps inference fast.
    """
    import json as _json

    cli = await _client()
    payload = {
        "model": ADMIN_MODEL,
        "messages": [{"role": "system", "content": _SYSTEM_PROMPT}] + history,
        "stream": True,
        "keep_alive": -1,
        "options": {
            "temperature": 0.7,
            "num_predict": 400,
            "num_ctx":     4096,
        },
    }

    placeholder = await msg.reply_text("✍ ...")
    buf = ""
    last_edit = 0.0
    last_text = ""
    EDIT_EVERY = 1.5  # seconds — Telegram caps edits at ~5/s; be conservative

    try:
        async with cli.stream(
            "POST", f"{OLLAMA_URL}/api/chat", json=payload, timeout=600.0
        ) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                raise RuntimeError(f"Ollama HTTP {resp.status_code}: {body[:300]!r}")
            async for line in resp.aiter_lines():
                if not line:
                    continue
                try:
                    data = _json.loads(line)
                except _json.JSONDecodeError:
                    continue
                chunk = (data.get("message") or {}).get("content", "")
                if chunk:
                    buf += chunk
                now = time.time()
                if (
                    buf
                    and now - last_edit > EDIT_EVERY
                    and buf != last_text
                ):
                    text = buf if len(buf) <= 3500 else buf[-3500:]
                    try:
                        await placeholder.edit_text(text + " ▋")
                        last_text = buf
                        last_edit = now
                    except Exception:  # noqa: BLE001 - rate-limited, ignore
                        pass
                if data.get("done"):
                    break
    except Exception:
        # Surface a final-state edit so the user isn't stuck on "✍ ..."
        if buf:
            try:
                await placeholder.edit_text(buf[-3500:])
            except Exception:
                pass
        raise

    final_text = (buf or "(пустой ответ)").strip()
    try:
        await placeholder.edit_text(final_text[-3500:])
    except Exception:
        pass

    # If the streamed text overflowed Telegram's 4096-char cap, send the rest
    # as follow-up messages so the user sees the full reply.
    if len(final_text) > 3500:
        for chunk in _chunks(final_text[3500:], 3500):
            await msg.reply_text(chunk)

    return final_text


def _chunks(text: str, size: int):
    """Split a long message into Telegram-safe chunks."""
    for i in range(0, len(text), size):
        yield text[i : i + size]


async def _handle_task(msg, prompt: str) -> None:
    """Run the task through the API and reply in human-readable Russian."""
    await msg.chat.send_action(action=ChatAction.TYPING)
    token = await _ensure_token()
    cli = await _client()

    try:
        r = await cli.post(
            f"{API_BASE}/api/run",
            json={
                "prompt": prompt,
                "planner_provider": "mock",
                "critic_provider":  "mock",
                "executor_provider":"local-agent",
                "execute": True,
            },
            headers=_auth_headers(token),
        )
    except httpx.RequestError as e:
        await msg.reply_text(f"❌ Не дозвонился до сервера: {e}")
        return

    if r.status_code == 401:
        global _jwt
        _jwt = None
        await msg.reply_text("🔑 Токен устарел — пришли запрос ещё раз.")
        return
    if r.status_code == 429:
        await msg.reply_text("⏳ Лимит на сегодня. Попробуй завтра или подкрути DAILY_TASK_QUOTA.")
        return
    if r.status_code != 200:
        await msg.reply_text(f"⚠ Сервер ответил {r.status_code}: {r.text[:300]}")
        return

    data  = r.json()
    score = data["critique"]["overall_score"]
    ready = data["ready_for_execution"]
    ex    = data.get("execution") or {}

    # ── Случай 1: план не одобрен — executor не запустился ────────────
    if not ready or not ex:
        weaknesses = data["critique"].get("weaknesses", [])
        contradictions = data["critique"].get("contradictions", [])
        reasons = "\n".join(
            f"  • {w}" for w in (weaknesses + contradictions)[:5]
        ) or "  • (без деталей)"
        await msg.reply_text(
            f"🟡 План не прошёл проверку безопасности (score {score}/100).\n"
            f"Причины:\n{reasons}\n\n"
            f"Я не запускал — двойной критик заблокировал. "
            f"Перефразируй задачу — попробую ещё раз."
        )
        return

    # ── Случай 2: исполнено — вытаскиваем что реально создано ─────────
    files_written: list[str] = []
    runs_output:   list[str] = []
    for step in ex.get("step_results", []):
        if step["status"] != "succeeded":
            continue
        out = step.get("output", "") or ""
        m = _FILENAME_IN_OUTPUT.search(out)
        if m:
            files_written.append(m.group(1))
        # run_python output looks like "exit_code=0\n<stdout>"
        if out.startswith("exit_code=0") and "\n" in out:
            tail = out.split("\n", 1)[1].strip()
            if tail:
                runs_output.append(tail[:300])

    lines: list[str] = ["✅ Готово."]
    if files_written:
        plural = "файлы" if len(files_written) > 1 else "файл"
        joined = ", ".join(f"`{f}`" for f in files_written)
        lines.append(f"Создал {plural}: {joined}")
        lines.append(f"Лежат в: workspace/anonymous/")
    if runs_output:
        lines.append("")
        lines.append("Запустил, вот что вышло:")
        for o in runs_output[:2]:
            lines.append(f"  {o}")
    if not files_written and not runs_output:
        lines.append(f"score {score}/100, шагов выполнено {len(ex.get('step_results', []))}.")

    await msg.reply_text("\n".join(lines))


# ── main ─────────────────────────────────────────────────────────────


def main() -> None:
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start",      cmd_start))
    app.add_handler(CommandHandler("help",       cmd_help))
    app.add_handler(CommandHandler("status",     cmd_status))
    app.add_handler(CommandHandler("usage",      cmd_usage))
    app.add_handler(CommandHandler("run",        cmd_run))
    app.add_handler(CommandHandler("admin",      cmd_admin))
    app.add_handler(CommandHandler("forget",     cmd_forget))
    app.add_handler(CommandHandler("exit_admin", cmd_exit_admin))
    # Любой текст без / — задача (или free-chat в админ-режиме)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_plain_text))
    log.info("two_brains telegram bot starting; upstream=%s user=%s", API_BASE, SERVICE_USER)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
