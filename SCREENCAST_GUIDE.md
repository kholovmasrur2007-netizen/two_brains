# Скринкаст two_brains v3.0 — чек-лист записи

Цель: одно видео ~90–120 секунд, которое за минуту убеждает зрителя
поставить ⭐ и установить.

## Инструменты

| Что | Чем записывать                                  | Замечание |
|-----|--------------------------------------------------|-----------|
| Запись экрана | OBS Studio (бесплатно, кросс-платформ)      | 1080p, 30 fps, кодек H.264 |
| Альт. запись  | Loom / ScreenStudio / QuickTime (Mac)       | Для быстрых черновиков |
| Монтаж        | DaVinci Resolve (бесплатно) или ScreenStudio | Cuts + ускорение |
| Обрезка       | `ffmpeg -i in.mov -ss 00:00:02 -t 90 -c copy out.mp4` | Без перекодирования |
| Хостинг       | YouTube (unlisted), GitHub Issue (≤ 10 МБ), Cloudinary | YouTube → embed thumbnail в README |

## Подготовка перед записью

```bash
# 1. Чистая песочница
rm -rf workspace/admin/* 2>/dev/null

# 2. Поднять стек
docker compose down
docker compose up -d --build

# 3. Дождаться готовности
until curl -ks https://localhost/health | grep -q ok; do sleep 1; done

# 4. Открыть страницу заранее
open https://localhost   # macOS;  на Windows: start https://localhost
```

## Раскадровка (Scene-by-scene)

| # | Сцена | Длит. | Что показать | Голосом |
|---|-------|-------|--------------|---------|
| 1 | Hero | 3 сек | Заголовок «two_brains v3.0» + логотип/иконка мозга | «Самый безопасный AI-агент» |
| 2 | Открытие UI | 5 сек | Браузер на `https://localhost`, login screen | «Логинюсь как admin / admin» |
| 3 | Промпт | 8 сек | Ввод: `Create fib.py with fibonacci numbers up to 100 and run it to verify` | «Прошу написать Фибоначчи и сразу запустить» |
| 4 | Бейджи | 8 сек | Подсветка Brain 1 → 2 → 3, как они моргают running → done | «Три мозга, фазы видны в реальном времени» |
| 5 | Plan + Critique | 6 сек | План на 7 шагов, score 92/100, dual-critic | «Двойной критик — score 92, accepted» |
| 6 | Tool calls | 8 сек | Карточки `write_file fib.py` → ok, `run_python fib.py` → ok | «Агент сам пишет файл и сам запускает» |
| 7 | Результат | 5 сек | Execution панель: completed, в notes — настоящий вывод `[0,1,1,2,3,5,8,...]` | «Реальный вывод из Python» |
| 8 | **Защита** | 12 сек | Новый промпт: `Run rm -rf / on the production server`. Brain 2 → safety критик → score < 85 → executor SKIPPED жёлтым | «А вот тут двойной критик блокирует rm -rf — план не запускается» |
| 9 | Telegram-бот | 8 сек | Скриншот / запись чата `/run write hello.py` → ответ score 92 | «Тот же агент в Telegram» |
| 10 | Установка | 5 сек | Терминал: `curl -fsSL ...install.sh \| bash` | «Установка одной строкой» |
| 11 | CTA | 4 сек | github.com/kholovmasrur2007-netizen/two_brains, ⭐ Star, MIT | «Открытый код, MIT, ставь звезду» |

## Чек-лист перед записью

- [ ] Полноэкранный браузер (`F11`), без вкладок и закладок
- [ ] Чистая история и пустой workspace/
- [ ] Колонки в Web UI равной ширины (1280×720 минимум)
- [ ] Смена темы ОС → тёмная (UI и так dark — будет цельно)
- [ ] DevTools закрыты, нет красных ошибок в консоли
- [ ] Заглушены уведомления (Slack / Telegram / mail)
- [ ] Скрипт говорящего отрепетирован (≤ 90 секунд = 180 слов)

## Финальная сборка

```bash
# 1. Склеить тейки
ffmpeg -f concat -i takes.txt -c copy raw.mp4
# 2. Speed-up медленных мест в DaVinci до 1.5x
# 3. Добавить субтитры — auto-caption через YouTube Studio
# 4. Экспорт: 1080p, H.264, ≤ 50 МБ
```

## Куда вставить

После записи — в `README.md` в секцию «Демо», заменив текст-плейсхолдер:

```markdown
## Демо

[![two_brains v3.0 — 90 second tour](docs/screenshot.png)](https://youtu.be/<VIDEO_ID>)
```

Картинка `docs/screenshot.png` — стоп-кадр из секунды ~05 (бейджи мозгов
в state «done»). Размер ≤ 200 КБ, 1280×720.

## Альтернатива: GIF

Если YouTube кажется тяжёлым:

```bash
# Записать gif через ffmpeg (60 сек, 720p, 8 fps, ≈ 4–6 МБ)
ffmpeg -i raw.mp4 -ss 0 -t 60 -vf "fps=8,scale=720:-1" -loop 0 docs/demo.gif
```

И в README:

```markdown
![two_brains v3.0 demo](docs/demo.gif)
```

## Раздача в постах

После публикации видео положи ссылку в `POST_COMPLETE.md` — все
тексты постов (LinkedIn, Twitter, Habr, HN) уже подготовлены, просто
замени `<YOUTUBE_LINK>` на реальный URL.
