#!/bin/bash
# two_brains v3.0 — VPS demo deploy.
#
# Run this on a fresh Linux VPS that already has Docker + Docker Compose
# installed and DNS for `demo.two-brains.ai` pointing at the host.
#
#   curl -fsSL https://raw.githubusercontent.com/kholovmasrur2007-netizen/two_brains/main/deploy-demo.sh | sudo bash
#
# Or copy the script to the server and run `./deploy-demo.sh`.

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}🚀 two_brains v3.0 — demo deploy${NC}"
echo

# ── 0. DNS instruction ───────────────────────────────────────────────
PUBLIC_IP=$(curl -s --max-time 4 https://api.ipify.org 2>/dev/null || echo "<this-server-IP>")
DEMO_DOMAIN="${DEMO_DOMAIN:-demo.two-brains.ai}"
echo -e "${YELLOW}DNS-проверка перед стартом:${NC}"
echo "    Создай A-запись в DNS-провайдере:"
echo "        ${DEMO_DOMAIN}   →   ${PUBLIC_IP}"
echo "    Дождись пока 'dig +short ${DEMO_DOMAIN}' вернёт ${PUBLIC_IP}."
echo "    Затем продолжай — сертификат будет на ${DEMO_DOMAIN}."
echo

# ── 1. Pre-flight checks ─────────────────────────────────────────────
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Docker не найден. Поставь его сначала: https://docs.docker.com/engine/install/${NC}"
    exit 1
fi
if ! docker compose version &> /dev/null; then
    echo -e "${RED}'docker compose' не работает. Поставь docker compose v2.${NC}"
    exit 1
fi
DOCKER_VERSION=$(docker --version | awk '{print $3}' | tr -d ',')
echo -e "${GREEN}✓ Docker $DOCKER_VERSION готов${NC}"
if ! command -v openssl &> /dev/null; then
    echo -e "${YELLOW}openssl не найден — самоподписанный cert не будет создан.${NC}"
fi
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}python3 нужен для генерации SECRET_KEY${NC}"
    exit 1
fi

# ── 2. Clone / update ────────────────────────────────────────────────
INSTALL_DIR="/opt/two-brains"
REPO="https://github.com/kholovmasrur2007-netizen/two_brains.git"

if [ -d "$INSTALL_DIR" ]; then
    echo "Обновляю $INSTALL_DIR ..."
    cd "$INSTALL_DIR"
    git pull
else
    echo "Клонирую в $INSTALL_DIR ..."
    git clone "$REPO" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# ── 3. .env ──────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
    cp .env.example .env

    echo
    echo -e "${YELLOW}Сейчас спрошу пару секретов. Жми Enter если хочешь пропустить.${NC}"

    read -p "ANTHROPIC_API_KEY (sk-ant-...): " ANTHROPIC_KEY
    if [ -n "$ANTHROPIC_KEY" ]; then
        echo "ANTHROPIC_API_KEY=$ANTHROPIC_KEY" >> .env
    fi

    read -p "OPENAI_API_KEY (sk-proj-..., можно пропустить): " OPENAI_KEY
    if [ -n "$OPENAI_KEY" ]; then
        echo "OPENAI_API_KEY=$OPENAI_KEY" >> .env
    fi

    # Random JWT secret if the user didn't set one.
    if ! grep -q "^SECRET_KEY=" .env || grep -q "^SECRET_KEY=please-change-me" .env; then
        NEW_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
        # Replace the placeholder line.
        sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$NEW_SECRET/" .env || \
        echo "SECRET_KEY=$NEW_SECRET" >> .env
    fi

    # Force production toggles for the demo.
    sed -i 's/^AUTH_ENABLED=.*/AUTH_ENABLED=true/' .env || echo "AUTH_ENABLED=true" >> .env
    sed -i 's|^USE_DB=.*|USE_DB=true|'              .env || echo "USE_DB=true"      >> .env

    echo -e "${GREEN}.env создан и подправлен.${NC}"
fi

# ── 4. Self-signed cert if no real one yet ──────────────────────────
if [ ! -f "nginx/certs/server.crt" ] || [ ! -f "nginx/certs/server.key" ]; then
    echo "Генерирую самоподписанный TLS-cert ..."
    mkdir -p nginx/certs
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout nginx/certs/server.key \
        -out    nginx/certs/server.crt \
        -subj   "/CN=demo.two-brains.ai" 2>/dev/null
fi

# ── 5. Bring it up ───────────────────────────────────────────────────
docker compose up -d --build

echo
echo -e "${GREEN}✅ Готово.${NC}"
echo "    https://${DEMO_DOMAIN}  (или https://${PUBLIC_IP})"
echo "    Логин по умолчанию: admin / admin (поменяй в /auth/me)"
echo
echo "Проверка живости:"
echo "    curl -k https://localhost/health"
echo "Логи:"
echo "    docker compose logs -f app"
echo
echo "Сервисы перезапускаются автоматически (restart: always) — ребут VPS не страшен."
