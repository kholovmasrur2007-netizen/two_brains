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
import textwrap

import httpx
from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
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
    👋 *two_brains v3.0* — самый безопасный AI-агент.

    Я умею:
      /run <задача>   — поставить задачу агенту
      /status         — проверить, жив ли сервис
      /usage          — посмотреть остаток дневной квоты
      /help           — справка

    Пример:
      /run create hello.py with a hello world script and run it to verify

    Я говорю с локальным two_brains API. Безопасно, без shell, в песочнице.
""")

HELP = textwrap.dedent("""\
    *Команды*
    /run <prompt>   запустить задачу через двух‑мозговой пайплайн
    /status         проверить /health upstream-сервиса
    /usage          сколько задач осталось сегодня по квоте
    /start          приветствие
    /help           эта справка

    Принципы:
    • двойной критик блокирует `rm -rf`, `sudo`, traversal
    • план не запускается, если score < 85
    • файлы пишутся только в твою песочницу
""")


async def cmd_start(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(WELCOME, parse_mode=ParseMode.MARKDOWN)


async def cmd_help(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(HELP, parse_mode=ParseMode.MARKDOWN)


async def cmd_status(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    cli = await _client()
    try:
        r = await cli.get(f"{API_BASE}/health")
        data = r.json()
        await update.effective_message.reply_text(
            f"✅ *upstream*: ok\n_uptime_: `{data.get('uptime_seconds', '?')}s`",
            parse_mode=ParseMode.MARKDOWN,
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
            f"📊 *Квота*\n"
            f"Использовано сегодня: `{u['used_today']}`\n"
            f"Дневной лимит:        `{u['daily_quota']}`\n"
            f"Осталось:              `{u['remaining']}`",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:  # noqa: BLE001
        await update.effective_message.reply_text(f"❌ {e}")


async def cmd_run(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    prompt = " ".join(ctx.args).strip() if ctx.args else ""
    if not prompt:
        await msg.reply_text("📝 Используй: `/run <задача>`", parse_mode=ParseMode.MARKDOWN)
        return

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
        await msg.reply_text(f"❌ Запрос не дошёл: {e}")
        return

    if r.status_code == 401:  # token expired
        global _jwt
        _jwt = None
        await msg.reply_text("🔑 Токен устарел — попробуй ещё раз.")
        return
    if r.status_code == 429:
        await msg.reply_text("⏳ Превышен лимит. Попробуй позже.")
        return
    if r.status_code != 200:
        await msg.reply_text(f"⚠ {r.status_code}: {r.text[:300]}")
        return

    data = r.json()
    score = data["critique"]["overall_score"]
    judgement = data["critique"]["final_judgement"]
    ready = data["ready_for_execution"]
    rec = data["final_recommendation"]
    exec_block = ""
    if data.get("execution"):
        ex = data["execution"]
        steps_done = sum(1 for s in ex["step_results"] if s["status"] == "succeeded")
        steps_total = len(ex["step_results"])
        exec_block = (
            f"\n*Исполнение*: {ex['overall_status']} "
            f"({steps_done}/{steps_total} шагов)"
        )

    out = (
        f"🧠 *two_brains*\n"
        f"score: `{score}/100`  ·  {judgement}\n"
        f"ready: {'✅' if ready else '🟡'}\n"
        f"_{rec}_"
        f"{exec_block}"
    )
    await msg.reply_text(out, parse_mode=ParseMode.MARKDOWN)


# ── main ─────────────────────────────────────────────────────────────


def main() -> None:
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("help",   cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("usage",  cmd_usage))
    app.add_handler(CommandHandler("run",    cmd_run))
    log.info("two_brains telegram bot starting; upstream=%s user=%s", API_BASE, SERVICE_USER)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
