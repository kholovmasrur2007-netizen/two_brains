# two_brains v3.0 — релизный пост

Готовые тексты для LinkedIn / Twitter / Hacker News. Скопируй и
запости — длинная версия для LinkedIn / Хабр, короткая для Twitter.

---

## 🇷🇺 Русский (LinkedIn / Хабр / Telegram-канал)

> **two_brains v3.0 — самый безопасный AI-агент теперь open source**
>
> Зарелизили v3.0 «Мировой лидер» — open-source AI-агент, который
> отказывается выполнять опасные действия **до** того, как до них
> доберётся.
>
> Чем он отличается от AutoGPT / BabyAGI / LangChain Agents:
>
> 🧠 **Двойной критик** — один проверяет план на логическую
> корректность, второй (`SafetyCritic`) ловит `rm -rf`, `sudo`,
> `chmod 777`, `curl|wget`, выходы из sandbox через `../`. План
> получает min-score из двух мнений; одного «уверенного» голоса
> мало, чтобы пробить защиту.
>
> 🛡 **Защитный bar 85+** — исполнитель просто не запускается,
> если совокупный score меньше 85. Это не предупреждение, это
> жёсткий стоп.
>
> 📦 **Песочница на пользователя** — каждому свой
> `workspace/<username>/`, traversal заблокирован, абсолютные
> пути запрещены, есть disk-space pre-flight (нельзя забить диск).
>
> ⏱ **Wall-clock 300s** — агент не зависнет, не начнёт жечь
> бюджет на бесконечный цикл.
>
> 🌐 **Web UI с лайв-стримом** — все 8 фаз пайплайна (planner →
> critic → executor → tool calls) видны в реальном времени.
>
> 📊 **Audit log + Prometheus metrics** — всё под контролем,
> любая операция трасируется.
>
> 🚀 **Установка за 2 минуты:**
>
> ```bash
> curl -fsSL https://raw.githubusercontent.com/kholovmasrur2007-netizen/two_brains/main/install.sh | bash
> ```
>
> Поднимает Docker-стек (FastAPI + PostgreSQL + nginx) с TLS,
> логином/паролем, per-user квотами и аудит-логом из коробки.
>
> ⭐ Всё MIT — ставь звёздочку, форкай, ломай:
> 👉 https://github.com/kholovmasrur2007-netizen/two_brains
>
> #AI #opensource #security #agent #autogpt #langchain #python

---

## 🇬🇧 English (Twitter long / LinkedIn EN)

> **two_brains v3.0 — the safest open-source AI agent**
>
> Just shipped v3.0. AutoGPT and friends will happily try to
> `rm -rf` your workspace if the model says so. We won't.
>
> 🧠 **Dual critic** — one checks correctness, a regex-driven
> SafetyCritic blocks `rm -rf`, `sudo`, `chmod 777`, `curl|wget`,
> path traversal. The combined score is the worst of the two.
>
> 🛡 **Hard execution bar at 85** — under threshold, the
> executor simply refuses to run.
>
> 📦 **Per-user sandboxes** with traversal protection and
> disk-space pre-flight checks.
>
> ⏱ **300s wall-clock timeout** — no runaway loops.
>
> 🌐 **Live WebSocket UI** — every phase + tool call streamed
> to the browser as it happens.
>
> 📊 Audit log, Prometheus metrics, JWT auth, daily quotas —
> SaaS-grade out of the box.
>
> 🚀 **One-line install:**
>
> ```bash
> curl -fsSL https://raw.githubusercontent.com/kholovmasrur2007-netizen/two_brains/main/install.sh | bash
> ```
>
> Brings up FastAPI + PostgreSQL + nginx with TLS in Docker.
>
> ⭐ MIT-licensed — fork it, break it, send PRs:
> 👉 https://github.com/kholovmasrur2007-netizen/two_brains
>
> #AI #opensource #security #agent #autogpt #langchain #python

---

## 🐦 Twitter (короткая версия, ≤280 символов)

> **🇷🇺**
> two_brains v3.0 — самый безопасный AI-агент в open source.
> Двойной критик блокирует `rm -rf`, `sudo`, traversal до запуска.
> Hard bar 85+. Песочница на юзера. 238 тестов.
> Установка за 2 минуты:
> 👉 github.com/kholovmasrur2007-netizen/two_brains
> #AI #opensource

> **🇬🇧**
> two_brains v3.0 just shipped — the safest OSS AI agent.
> Dual critic blocks `rm -rf`, `sudo`, traversal *before* execution.
> Hard score bar at 85+. Per-user sandbox. 238 tests, CI green.
> 👉 github.com/kholovmasrur2007-netizen/two_brains
> #AI #opensource #security

---

## 📢 Hacker News title

> **Show HN: two_brains v3.0 – open-source AI agent with a dual-critic
> safety pass that blocks `rm -rf`, `sudo`, and sandbox-traversal before
> execution**
