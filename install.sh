#!/bin/bash
# two_brains v3.0 — one-line installer.
#
#   curl -fsSL https://raw.githubusercontent.com/kholovmasrur2007-netizen/two_brains/main/install.sh | bash
#
# Or run locally:
#
#   chmod +x install.sh && ./install.sh
#
# Clones (or updates) the repo into ~/two_brains, copies .env.example to
# .env if missing, and brings the docker-compose stack up.

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}🚀 two_brains v3.0 installer${NC}"

if ! command -v docker &> /dev/null; then
    echo -e "${RED}Docker не найден. Установи docker и docker compose: https://docs.docker.com/get-docker/${NC}"
    exit 1
fi

REPO="https://github.com/kholovmasrur2007-netizen/two_brains"
DIR="$HOME/two_brains"

if [ -d "$DIR" ]; then
    echo "Обновляю существующую установку в $DIR ..."
    cd "$DIR"
    git pull
else
    echo "Клонирую $REPO в $DIR ..."
    git clone "$REPO" "$DIR"
    cd "$DIR"
fi

if [ ! -f ".env" ]; then
    cp .env.example .env
    echo -e "${RED}Создан .env из шаблона. Отредактируй его (SECRET_KEY, ANTHROPIC_API_KEY и т.д.)${NC}"
    read -p "Нажми Enter, когда .env готов..." _unused
fi

docker compose up -d --build
echo -e "${GREEN}✅ Запущено. Открой https://localhost (логин: admin / admin при первом старте).${NC}"
