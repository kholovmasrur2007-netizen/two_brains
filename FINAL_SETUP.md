# two_brains v3.0 — финальная сборка к запуску

Семь оставшихся ручных шагов. Каждый расписан так, чтобы можно
было выполнить копированием команд. Время на всё — **~10 минут**
без учёта записи скринкаста.

| # | Шаг | Время | Куда |
|--:|-----|------:|------|
| 1 | Создать Telegram-бота | 1 мин | `@BotFather` |
| 2 | Купить домен и поднять DNS | 5 мин | Cloudflare / Namecheap |
| 3 | Запустить `deploy-demo.sh` на VPS | 2 мин | твой сервер |
| 4 | Записать скринкаст | 30 мин | OBS + ffmpeg |
| 5 | Загрузить видео на YouTube | 3 мин | youtube.com |
| 6 | Опубликовать посты | 10 мин | LinkedIn / Twitter / HN / Хабр |
| 7 | Поставить ⭐ на репо | 3 секунды | github.com |

> Один скрипт берёт на себя несколько шагов:
> - **`setup_telegram.sh`** — добавляет токен бота в `.env` и проверяет compose
> - **`deploy-demo.sh`** — DNS-подсказка, SECRET_KEY, certbot, поднятие стека
> - **`one_click_post.sh`** — выводит готовые тексты + открывает все нужные вкладки

---

## 1. Создать Telegram-бота через `@BotFather`

1. Открой в Telegram **[@BotFather](https://t.me/BotFather)**.
2. Отправь `/newbot`.
3. Имя бота: `two_brains` (или своё).
4. Username: `two_brains_bot` (если занят — добавь суффикс).
5. **BotFather пришлёт токен вида** `1234567890:ABCdefGhIJK...` — скопируй.

(Опционально, чтобы профиль выглядел красиво)
- `/setdescription` → «Самый безопасный AI-агент. Двойной критик блокирует rm -rf и traversal до запуска.»
- `/setabouttext` → «two_brains v3.0»
- `/setuserpic` → загрузи иконку
- `/setjoingroups` → `Disable` (если бот только для DM)
- `/setprivacy` → `Enable`

После — запускай:
```bash
./setup_telegram.sh
```
Скрипт спросит токен и пропишет всё в `.env`.

## 2. Купить домен + поднять DNS

**Самое простое — Cloudflare** (бесплатный план, моментальный DNS):

1. Зарегистрируйся на [cloudflare.com](https://cloudflare.com).
2. Купи домен в `Domain registration` (около $10/год для `.ai`,
   `.com` дешевле). Или купи на [Namecheap](https://www.namecheap.com)
   и переключи на Cloudflare DNS-сервера.
3. Узнай публичный IP своего VPS:
   ```bash
   curl https://api.ipify.org
   ```
4. В Cloudflare добавь A-запись:

   | Type | Name | Content (IP) | Proxy | TTL |
   |------|------|--------------|-------|-----|
   | A    | demo | `<IP-VPS>`   | DNS only (серый облачко) | Auto |

5. Подожди 1-2 минуты, проверь:
   ```bash
   dig +short demo.two-brains.ai
   ```
   Должен вернуться твой IP.

> **Не используешь Cloudflare?** То же самое в Namecheap →
> `Advanced DNS` → `Add new record` → A-record, host `demo`,
> value — IP, TTL `Automatic`.

## 3. Запустить `deploy-demo.sh` на VPS

Минимальные требования к VPS: **Ubuntu 22.04+, 2 vCPU, 2 GB RAM, 20 GB SSD,
Docker + docker-compose v2**. Любой $5-VPS у Hetzner / DigitalOcean / Vultr.

```bash
ssh user@<VPS-IP>

# (если Docker не установлен)
curl -fsSL https://get.docker.com | sudo sh

# Запуск автоустановщика
curl -fsSL https://raw.githubusercontent.com/kholovmasrur2007-netizen/two_brains/main/deploy-demo.sh \
    | DEMO_DOMAIN=demo.two-brains.ai sudo -E bash
```

Скрипт сам:
- проверит Docker и openssl
- покажет твой публичный IP и инструкцию по DNS
- сгенерирует `SECRET_KEY` (32 байта random hex)
- спросит `ANTHROPIC_API_KEY` (можно пропустить — local-agent работает офлайн)
- сгенерирует self-signed cert (или подскажет команду для Let's Encrypt)
- поднимет docker-compose с `restart: always`

Через ~30 секунд: `https://demo.two-brains.ai` → login `admin / admin`.

## 4. Записать скринкаст

Полный сценарий — в [`SCREENCAST_GUIDE.md`](SCREENCAST_GUIDE.md).

Краткая выжимка:
```bash
# Подготовка
docker compose down && docker compose up -d --build
rm -rf workspace/admin/*

# Запись (OBS Studio, F11 на браузере, 1080p / 30 fps / 60 сек)
# Или быстрый способ через ffmpeg на macOS:
ffmpeg -f avfoundation -i "1:0" -t 90 -c:v h264 -crf 23 raw.mp4

# Превратить mp4 → gif для README (≤ 5 МБ):
ffmpeg -i raw.mp4 -ss 0 -t 60 -vf "fps=8,scale=720:-1" -loop 0 docs/demo.gif
```

## 5. Загрузить на YouTube

1. [studio.youtube.com](https://studio.youtube.com) → `Создать` → `Загрузить видео`
2. Заголовок: `two_brains v3.0 — самый безопасный AI-агент в open source`
3. **Видимость:** `Не указано (unlisted)` — так покажется только по ссылке
4. После загрузки скопируй `https://youtu.be/<ID>` и:
   ```bash
   # Заменить во всех постах
   sed -i 's|<YOUTUBE_LINK>|https://youtu.be/<ID>|g' POST_COMPLETE.md
   ```

## 6. Опубликовать посты

Тексты готовы в [`POST_COMPLETE.md`](POST_COMPLETE.md).

Запусти:
```bash
./one_click_post.sh
```
Скрипт откроет в браузере **5 вкладок** одновременно:
- LinkedIn (compose)
- Twitter (compose)
- Hacker News (submit)
- Хабр (создать пост)
- GitHub Releases (на случай если понадобится показать)

И выведет готовые тексты в терминал — копируй и вставляй.

Чек-лист публикации (отмечать руками после публикации):
- [ ] LinkedIn — длинная RU версия
- [ ] Twitter — 280 символов RU + EN тред
- [ ] Hacker News — `Show HN: ...` + первый комментарий
- [ ] Хабр — длинный пост с диаграммами
- [ ] r/MachineLearning или r/programming — короткая версия
- [ ] awesome-ai-agents — submit PR

## 7. Поставить ⭐ на репо

[github.com/kholovmasrur2007-netizen/two_brains](https://github.com/kholovmasrur2007-netizen/two_brains) → **Star** в правом верхнем углу.

Поделись со знакомыми — каждая звезда поднимает в trending.

---

## Сводка скриптов

| Скрипт | Что делает | Запускать когда |
|--------|-----------|-----------------|
| `setup_telegram.sh` | Записывает Telegram-токен в `.env`, проверяет compose | После шага 1 (получил токен) |
| `deploy-demo.sh` | Полный VPS-деплой | На сервере, после шагов 1-2 |
| `one_click_post.sh` | Открывает соц-сети + печатает посты | После шага 5 (видео готово) |

Все три исполняемые (`chmod +x`), запускаются простым `./script.sh`.
