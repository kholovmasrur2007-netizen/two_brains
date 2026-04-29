#!/bin/bash
# two_brains — Telegram bot setup helper.
#
#   ./setup_telegram.sh
#
# Запускать в корне проекта. Скрипт:
#   1. Спрашивает токен у @BotFather (если ENV TELEGRAM_BOT_TOKEN не задан).
#   2. Спрашивает пароль для сервисного аккаунта бота.
#   3. Пишет всё в .env (создавая его из .env.example при необходимости).
#   4. Проверяет, что telegram_bot/bot.py есть и сервис прописан в compose.
#   5. Печатает следующую команду запуска.

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}🤖 two_brains — Telegram bot setup${NC}"
echo

# ── 0. Sanity: запускаем из корня проекта? ───────────────────────────
if [ ! -f "docker-compose.yml" ] || [ ! -d "telegram_bot" ]; then
    echo -e "${RED}Запускай из корня проекта two_brains (там docker-compose.yml и папка telegram_bot/).${NC}"
    exit 1
fi

# ── 1. .env ──────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo -e "${YELLOW}Создал .env из .env.example.${NC}"
    else
        touch .env
    fi
fi

# ── 2. Token ─────────────────────────────────────────────────────────
TOKEN="${TELEGRAM_BOT_TOKEN:-}"
if [ -z "$TOKEN" ]; then
    echo -e "${YELLOW}Получи токен у @BotFather:${NC} https://t.me/BotFather"
    echo "  /newbot → имя → username → BotFather пришлёт токен 1234567890:ABC..."
    echo
    read -p "Вставь токен сюда: " TOKEN
fi

if [[ ! "$TOKEN" =~ ^[0-9]{8,}:[A-Za-z0-9_-]{20,}$ ]]; then
    echo -e "${RED}Токен не похож на формат BotFather. Должен быть 'NUMBERS:LETTERS'.${NC}"
    echo "Пример: 1234567890:ABCdefGhIJKlmnoPQRsTUvwxYZ"
    exit 1
fi

# ── 3. Пароль для сервисного аккаунта ────────────────────────────────
SVCPASS="${TWOBRAINS_BOT_PASSWORD:-}"
if [ -z "$SVCPASS" ]; then
    SVCPASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(20))" 2>/dev/null || \
              echo "bot-$(date +%s)")
    echo -e "${YELLOW}Сгенерировал случайный пароль для сервисного аккаунта 'bot':${NC} $SVCPASS"
fi

# ── 4. Запись в .env ─────────────────────────────────────────────────
upsert_env() {
    local key="$1"
    local val="$2"
    if grep -q "^${key}=" .env 2>/dev/null; then
        # Используем '|' как разделитель — токен может содержать '/'.
        sed -i.bak "s|^${key}=.*|${key}=${val}|" .env && rm -f .env.bak
    else
        echo "${key}=${val}" >> .env
    fi
}

upsert_env TELEGRAM_BOT_TOKEN     "$TOKEN"
upsert_env TWOBRAINS_BOT_USERNAME "bot"
upsert_env TWOBRAINS_BOT_PASSWORD "$SVCPASS"

echo -e "${GREEN}✓ Записал в .env: TELEGRAM_BOT_TOKEN, TWOBRAINS_BOT_USERNAME, TWOBRAINS_BOT_PASSWORD${NC}"

# ── 5. Проверка docker-compose.yml ────────────────────────────────────
if ! grep -q '^\s*bot:' docker-compose.yml; then
    echo -e "${YELLOW}Сервис 'bot' не найден в docker-compose.yml.${NC}"
    echo "  Открой docker-compose.yml вручную и добавь блок 'bot:'."
    echo "  Шаблон есть в README.telegram.md."
else
    echo -e "${GREEN}✓ Сервис 'bot' уже прописан в docker-compose.yml${NC}"
fi

# ── 6. Проверка bot.py ───────────────────────────────────────────────
if [ ! -f "telegram_bot/bot.py" ]; then
    echo -e "${RED}telegram_bot/bot.py отсутствует — должен быть в репо.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ telegram_bot/bot.py на месте${NC}"

# ── 7. Подсказка по запуску ──────────────────────────────────────────
echo
echo -e "${CYAN}Готово. Запускай бота:${NC}"
echo
echo "    docker compose --profile bot up -d --build bot"
echo
echo "Логи в реальном времени:"
echo "    docker compose logs -f bot"
echo
echo "После запуска: открой Telegram → найди своего бота → /start"
echo
echo -e "${YELLOW}Совет:${NC} перед стартом бота создай в API сервисного юзера 'bot' с тем же паролем."
echo "    POST /auth/register с заголовком Authorization: Bearer <admin-jwt>"
echo "    {\"username\":\"bot\",\"password\":\"$SVCPASS\",\"is_admin\":false}"
