# two_brains v3.0 — готовые посты с реальными ссылками

Скопировал — отредактировал плейсхолдер `<YOUTUBE_LINK>` (когда видео
будет готово) — запостил.

**Реальные ссылки уже вставлены:**
- 🔗 Release: https://github.com/kholovmasrur2007-netizen/two_brains/releases/tag/v3.0.0
- 📦 Repo: https://github.com/kholovmasrur2007-netizen/two_brains
- 🌐 Demo: https://demo.two-brains.ai (DNS настроится при первом деплое)
- 💬 Bot: `@two_brains_bot` в Telegram (после `/newbot`)

---

## 📌 LinkedIn / Хабр / Telegram-канал (RU, длинная версия)

> 🚀 **Зарелизили two_brains v3.0** — open-source AI-агент, который
> отказывается выполнять опасные действия **до** того, как до них доберётся.
>
> 🎯 **Ключевая идея.** AutoGPT, BabyAGI и стандартные LangChain Agents
> охотно выполнят `rm -rf /workspace`, если так "решит модель". Мы — нет.
>
> 🧠 **Двойной критик.** Один проверяет план на логическую корректность,
> второй (`SafetyCritic`) на регулярках ловит:
> • `rm -rf`, `sudo`, `chmod 777`
> • `curl|wget`, `python -m http.server`, `subprocess`/`os.system`
> • выходы из sandbox через `../`, `/c:`
> • расплывчатые критерии типа "should work / hopefully / maybe"
> • запись файлов без декларации рисков
>
> Совокупный score = `min(primary, safety)`. Один уверенный голос не пробьёт защиту.
>
> 🛡 **Hard execution bar = 85.** Под порогом — executor просто отказывается
> запускаться. Это не warning, это жёсткий стоп.
>
> 📦 **Per-user sandbox.** Каждому юзеру свой `workspace/<username>/`,
> `..` блокируется до I/O, абсолютные пути запрещены, есть disk-space
> pre-flight (нельзя забить диск).
>
> ⏱ **Wall-clock 300s timeout.** Агент не зависнет на бесконечный цикл.
>
> 🌐 **Web UI с лайв-стримом** через WebSocket: видны все 8 фаз пайплайна
> (planner → critic → executor → tool calls → result) в реальном времени.
>
> 📊 **Audit log + Prometheus metrics + JWT auth + дневные квоты.**
> SaaS-grade из коробки.
>
> 💬 **Telegram-бот.** Полный пайплайн прямо в чате — `/run create
> hello.py`, и через секунду агент отвечает.
>
> 🚀 **Установка за 2 минуты:**
>
> ```bash
> curl -fsSL https://raw.githubusercontent.com/kholovmasrur2007-netizen/two_brains/main/install.sh | bash
> ```
>
> Поднимает Docker-стек (FastAPI + PostgreSQL + nginx + Telegram-бот) с TLS,
> логином/паролем, per-user квотами и аудит-логом.
>
> 🎬 90-секундное демо: <YOUTUBE_LINK>
> ⭐ Звёздочки и форки — на: https://github.com/kholovmasrur2007-netizen/two_brains
> 📋 Release notes: https://github.com/kholovmasrur2007-netizen/two_brains/releases/tag/v3.0.0
>
> Всё MIT. 238 тестов, CI зелёный на Python 3.11+3.12.
>
> #AI #opensource #security #agent #autogpt #langchain #python #devops

---

## 📌 LinkedIn / Twitter / HN (EN, длинная версия)

> 🚀 **Just shipped two_brains v3.0** — an open-source AI agent that
> *refuses* to execute dangerous actions instead of asking nicely.
>
> 🎯 The premise. AutoGPT and friends will happily try to `rm -rf` your
> workspace if the model says so. We won't.
>
> 🧠 **Dual critic.** One critic checks correctness, a regex-driven
> `SafetyCritic` blocks:
> • `rm -rf`, `sudo`, `chmod 777`
> • `curl|wget`, `python -m http.server`, `subprocess`/`os.system`
> • path traversal (`../`, `/c:`, drive prefixes)
> • fuzzy success criteria ("should work", "hopefully", "maybe")
> • writes without declared risks
>
> Combined score = `min(primary, safety)`. A confident-sounding correctness
> pass cannot override a safety failure.
>
> 🛡 **Hard execution bar at 85.** Below threshold the executor flat-out
> refuses to run. Not a warning — a wall.
>
> 📦 **Per-user sandbox.** Each user gets `workspace/<username>/`. `..`
> rejected before I/O, absolute paths forbidden, disk-space pre-flight
> kills the "fill the disk" DoS class.
>
> ⏱ **300 s wall-clock timeout.** No runaway loops, no surprise bills.
>
> 🌐 **Live WebSocket UI.** Every pipeline phase + tool call streamed to
> the browser as it happens.
>
> 📊 Audit log, Prometheus metrics, JWT auth, daily quotas — SaaS-grade out of the box.
>
> 💬 **Telegram bot included.** Same pipeline, in Telegram chat.
>
> 🚀 **One-line install:**
>
> ```bash
> curl -fsSL https://raw.githubusercontent.com/kholovmasrur2007-netizen/two_brains/main/install.sh | bash
> ```
>
> Brings up FastAPI + PostgreSQL + nginx + Telegram bot in Docker with TLS.
>
> 🎬 90-second demo: <YOUTUBE_LINK>
> ⭐ MIT-licensed, fork it, break it, send PRs:
>     https://github.com/kholovmasrur2007-netizen/two_brains
> 📋 Release notes:
>     https://github.com/kholovmasrur2007-netizen/two_brains/releases/tag/v3.0.0
>
> 238 tests, CI green on Python 3.11 + 3.12.
>
> #AI #opensource #security #agent #autogpt #langchain #python #devops

---

## 🐦 Twitter (≤ 280 символов)

### Русская версия:

> 🚀 two_brains v3.0 — самый безопасный AI-агент в open source.
> Двойной критик блокирует `rm -rf`, `sudo`, traversal до запуска.
> Hard bar 85+. Sandbox на юзера. Telegram-бот в комплекте. 238 тестов.
>
> 👉 github.com/kholovmasrur2007-netizen/two_brains
> #AI #opensource

### English:

> 🚀 two_brains v3.0 just shipped — safest OSS AI agent.
> Dual critic blocks `rm -rf`, `sudo`, traversal before execution.
> Hard bar at 85+. Per-user sandbox. Telegram bot. 238 tests, CI green.
>
> 👉 github.com/kholovmasrur2007-netizen/two_brains
> #AI #opensource #security

---

## 📰 Hacker News

**Title (≤ 80 chars):**

> Show HN: two_brains – AI agent that blocks rm -rf and traversal before run

**First comment (HN style — short, no marketing):**

> Author here. The interesting bit is the dual critic: a deterministic
> regex-driven SafetyCritic runs alongside the LLM critic, and the combined
> score is `min(both)`. So even if the model is 100% confident the plan
> is fine, the SafetyCritic can drag it under the 85-point execution bar.
>
> Other things I'm proud of:
> - per-user sandbox with traversal protection (parametrised tests cover
>   `/etc/passwd`, `C:/Windows`, `..\\escape`, multi-level escapes)
> - 300 s wall-clock timeout in the agent loop (no runaway billing)
> - disk-space pre-flight in `write_file`
> - WebSocket per-IP rate limit (slowapi only covers REST)
>
> All of it MIT, 238 tests, CI green on 3.11 + 3.12.
> Repo: https://github.com/kholovmasrur2007-netizen/two_brains
> Release notes: https://github.com/kholovmasrur2007-netizen/two_brains/releases/tag/v3.0.0
>
> Happy to answer questions about the architecture or why I picked these
> particular safety primitives.

---

## 🧵 Хабр (длинный пост)

Хабр любит длинный технический разбор. Используй RU длинную версию
сверху как **введение**, а потом раскрой каждый блок отдельной секцией:

1. **Проблема: модели легко уговорить на rm -rf** — пример с AutoGPT
2. **Архитектура из 3 мозгов** — диаграмма (Planner → Critic → Executor)
3. **SafetyCritic в деталях** — таблица паттернов и сколько score снимает
4. **Защитный bar 85** — почему именно 85, как комбинируется с обычным критиком
5. **Per-user sandbox** — таблица параметризованных тестов
6. **Wall-clock timeout, disk-space, WebSocket rate limit** — три "малых" защиты
7. **Web UI с WebSocket** — скриншот, как видны фазы
8. **Telegram-бот** — скриншот чата
9. **Деплой одной строкой** — `curl ...install.sh`
10. **Цифры**: 238 тестов, 6 700 строк, CI 3.11+3.12, 8 фаз, 5 tool-функций
11. **Всё MIT**, ссылка на репо

**Тег:** `[Show GH] two_brains v3.0 — AI-агент с двойным критиком`

---

## 📅 Чек-лист публикации

- [ ] Записан скринкаст (по [`SCREENCAST_GUIDE.md`](SCREENCAST_GUIDE.md))
- [ ] Видео загружено на YouTube как **unlisted**
- [ ] `<YOUTUBE_LINK>` заменён на реальный URL во всех 4 шаблонах
- [ ] Скриншот ⌚ дабовлен в `docs/screenshot.png` и закоммичен
- [ ] DNS на `demo.two-brains.ai` поднят, `deploy-demo.sh` отработал
- [ ] LinkedIn-пост опубликован
- [ ] Twitter-тред (1 пост + 2 thread-replies с примерами)
- [ ] Hacker News — Show HN с правильным title
- [ ] Хабр (длинный пост) опубликован
- [ ] Опубликован Telegram-канал релиза (если есть)
- [ ] Коммент в r/MachineLearning или r/programming с прямой ссылкой
- [ ] Сабмит на awesome-ai-agents / awesome-llm-agents
