"""Render the four Telegram-style chat frames from telegram_demo.html into PNGs.

Run:
    python docs/capture_telegram.py

Output:
    docs/screenshots/telegram-01-task.png
    docs/screenshots/telegram-02-admin.png
    docs/screenshots/telegram-03-safety.png
    docs/screenshots/telegram-04-service.png
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
HTML = ROOT / "telegram_demo.html"
OUT = ROOT / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)

FRAMES = [
    ("#frame1", "telegram-01-task.png"),
    ("#frame2", "telegram-02-admin.png"),
    ("#frame3", "telegram-03-safety.png"),
    ("#frame4", "telegram-04-service.png"),
]


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_context(
            viewport={"width": 1200, "height": 1400},
            device_scale_factor=2,           # retina-quality crops for README
        ).new_page()

        page.goto(HTML.as_uri(), wait_until="networkidle")

        for selector, name in FRAMES:
            page.locator(selector).screenshot(
                path=str(OUT / name),
                omit_background=False,
            )
            print(f"saved {name}")

        browser.close()


if __name__ == "__main__":
    main()
