#!/bin/bash
# two_brains — one-click "post the launch" helper.
#
#   ./one_click_post.sh
#
# Печатает готовые посты в терминал и открывает в браузере 5 вкладок:
#   • LinkedIn (compose feed)
#   • Twitter/X (compose tweet)
#   • Hacker News (submit form)
#   • Хабр (создать пост)
#   • GitHub Releases (наша ссылка для копирования)
#
# Кросс-платформенно: macOS (open), Linux (xdg-open), WSL/Windows (cmd.exe /c start).

set -e

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

REPO="https://github.com/kholovmasrur2007-netizen/two_brains"
RELEASE="$REPO/releases/tag/v3.0.0"
POST_FILE="POST_COMPLETE.md"

if [ ! -f "$POST_FILE" ]; then
    echo "Не найден $POST_FILE. Запускай скрипт из корня проекта two_brains."
    exit 1
fi

# ── Detect "open URL" command for the host OS ────────────────────────
open_url() {
    local url="$1"
    if   command -v xdg-open  &>/dev/null;             then xdg-open  "$url" &>/dev/null &
    elif command -v open      &>/dev/null;             then open      "$url" &>/dev/null &
    elif command -v cmd.exe   &>/dev/null;             then cmd.exe /c start "" "$url" &>/dev/null &
    elif command -v powershell.exe &>/dev/null;        then powershell.exe -c "Start-Process '$url'" &>/dev/null &
    else
        echo "  → открой вручную: $url"
    fi
}

# ── Pretty banner ────────────────────────────────────────────────────
echo -e "${CYAN}🚀 two_brains v3.0 — one-click post${NC}"
echo
echo -e "Релиз: ${GREEN}$RELEASE${NC}"
echo -e "Репо:  ${GREEN}$REPO${NC}"
echo

# ── Print the posts so the user can copy-paste ───────────────────────
echo -e "${YELLOW}─── Готовые тексты ниже (полные версии в $POST_FILE) ───${NC}"
echo
echo -e "${CYAN}► Twitter (RU, 280 символов):${NC}"
cat <<'EOF'
🚀 two_brains v3.0 — самый безопасный AI-агент в open source.
Двойной критик блокирует rm -rf, sudo, traversal до запуска.
Hard bar 85+. Sandbox на юзера. Telegram-бот в комплекте. 238 тестов.

👉 github.com/kholovmasrur2007-netizen/two_brains
#AI #opensource
EOF
echo
echo -e "${CYAN}► Twitter (EN, 280 символов):${NC}"
cat <<'EOF'
🚀 two_brains v3.0 just shipped — safest OSS AI agent.
Dual critic blocks rm -rf, sudo, traversal before execution.
Hard bar at 85+. Per-user sandbox. Telegram bot. 238 tests, CI green.

👉 github.com/kholovmasrur2007-netizen/two_brains
#AI #opensource #security
EOF
echo
echo -e "${CYAN}► Hacker News title:${NC}"
echo "Show HN: two_brains – AI agent that blocks rm -rf and traversal before run"
echo
echo -e "${YELLOW}Полные длинные версии (LinkedIn, Хабр, HN first comment):${NC}"
echo "    $POST_FILE"
echo

# ── Pause before opening tabs ────────────────────────────────────────
read -p "Нажми Enter, чтобы открыть все 5 вкладок (LinkedIn, Twitter, HN, Хабр, Releases)..." _

# ── Open the tabs ────────────────────────────────────────────────────
echo
echo "Открываю вкладки в браузере..."

# 1. LinkedIn — compose post in the feed
open_url "https://www.linkedin.com/feed/?shareActive=true"

# 2. Twitter / X — compose tweet
open_url "https://twitter.com/compose/post"

# 3. Hacker News — submit form
open_url "https://news.ycombinator.com/submit"

# 4. Хабр — create new post
open_url "https://habr.com/ru/article/edit/"

# 5. GitHub Releases — for reference / star prompt
open_url "$RELEASE"

echo
echo -e "${GREEN}✅ Всё открыто. Копируй тексты сверху в каждую вкладку.${NC}"
echo
echo -e "Чек-лист после публикации (отметь сам):"
echo "    [ ] LinkedIn"
echo "    [ ] Twitter"
echo "    [ ] Hacker News"
echo "    [ ] Хабр"
echo "    [ ] r/MachineLearning или r/programming"
echo "    [ ] awesome-ai-agents (PR)"
echo
echo "Когда видео будет на YouTube, замени плейсхолдер:"
echo "    sed -i 's|<YOUTUBE_LINK>|https://youtu.be/<ID>|g' POST_COMPLETE.md"
