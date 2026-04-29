# two_brains — Telegram-бот

Тонкий бот-фронтенд, ставит задачи в локальный API two_brains и
отдаёт ответ обратно в чат. Работает в той же docker-compose сети,
что и основной сервис.

## 1. Получить токен у `@BotFather`

1. Открой [t.me/BotFather](https://t.me/BotFather) в Telegram.
2. `/newbot` → задай имя и username (`@two_brains_bot` или своё).
3. BotFather пришлёт токен вида `1234567890:ABCdefGhIJK...`. Сохрани.

(Опционально) `/setdescription`, `/setabouttext`, `/setuserpic` — для
красивого профиля. Для приватного бота настрой `/setjoingroups off` и
`/setprivacy enabled`.

## 2. Сделать сервисный аккаунт в two_brains

Бот идёт в API под отдельным логином, чтобы аудит-лог различал
ручные запуски и тех, что пришли через Telegram.

```bash
# Зайди в контейнер app или используй curl с токеном админа.
docker compose exec app python -m app.main register-bot 2>/dev/null || \
curl -k -X POST https://localhost/auth/register \
    -H "Authorization: Bearer <admin-jwt>" \
    -H "Content-Type: application/json" \
    -d '{"username":"bot","password":"<long-password>","is_admin":false}'
```

Запиши логин и пароль — они уйдут в `.env` бота.

## 3. Прописать переменные в `.env`

В корне проекта (там же где `docker-compose.yml`) дополни `.env`:

```
# ── Telegram bot ──────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGhIJKlmNopQrStUvWxYz
TWOBRAINS_BOT_USERNAME=bot
TWOBRAINS_BOT_PASSWORD=<тот же пароль, что задал на шаге 2>
```

## 4. Запустить

Сервис помечен профилем `bot`, чтобы случайно не стартовать без токена.

```bash
docker compose --profile bot up -d --build bot
docker compose logs -f bot     # должно появиться "logged in as bot"
```

Чтобы бот всегда поднимался вместе со стеком, убери строку `profiles: ["bot"]`
из `docker-compose.yml`.

## 5. Команды бота в чате

```
/start    приветствие + краткая справка
/help     полный список команд
/run      /run write hello.py with hello world
/status   проверить liveness upstream-сервиса
/usage    остаток дневной квоты
```

Пример:

```
> /run create fib.py with fibonacci numbers up to 100 and run it to verify

🧠 two_brains
score: 92/100  ·  accepted
ready: ✅
Plan is ready to execute.
Исполнение: completed (2/2 шагов)
```

## 6. Как это устроено

```
   Telegram   ──HTTPS──▶   bot.py   ──HTTP──▶   app:8000
                              │                     │
                              ↓                     ↓
                    httpx    /api/run     two_brains pipeline
                                          (planner → critic → executor)
```

Бот живёт в той же docker-сети, поэтому ходит на upstream
по приватному имени `app:8000`. Снаружи бот доступа к `app` не даёт —
вся фильтрация делается на стороне Telegram.

## 7. Безопасность

- Бот авторизуется в API под сервисным логином `bot`
- Все вызовы идут с JWT-токеном; на 401 бот молча релогинится
- Per-user sandbox у бота тоже свой (`workspace/bot/`)
- Дневная квота применяется как обычно (`DAILY_TASK_QUOTA`)
- Все запросы попадают в audit-лог с `username=bot`

## 8. Локальный запуск без Docker

```bash
cd telegram_bot
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN=...
export TWOBRAINS_URL=http://localhost:8000
export TWOBRAINS_USERNAME=bot
export TWOBRAINS_PASSWORD=...
python bot.py
```
