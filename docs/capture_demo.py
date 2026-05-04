"""Generate static demo screenshots of the two_brains Web UI.

Drives a headless Edge browser through Playwright, runs a real task
end-to-end, and saves PNGs of the key states for the README.

Run:
    python docs/capture_demo.py

Requires:
    pip install playwright
    (Microsoft Edge already installed by default on Windows)
    Web server live at http://127.0.0.1:8000
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

SCREENSHOTS = Path(__file__).resolve().parent / "screenshots"
SCREENSHOTS.mkdir(parents=True, exist_ok=True)


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 1600})
        page = context.new_page()

        # ── 1. Landing — fresh UI, no run yet ────────────────────────────
        page.goto("http://127.0.0.1:8000", wait_until="networkidle")
        # Wait for provider list to populate.
        page.wait_for_function(
            "document.querySelector('#executor option[value=\"local-agent\"]') !== null",
            timeout=10000,
        )
        page.screenshot(path=str(SCREENSHOTS / "01-landing.png"), full_page=True)
        print("saved 01-landing.png")

        # ── 2. Type a task and hit Run ───────────────────────────────────
        page.fill(
            "#prompt",
            "Write fib.py with fibonacci numbers up to 100 and run it to verify",
        )
        page.click("#run-btn")

        # Wait until the executor finishes (the badge text becomes "done")
        page.wait_for_selector(
            "#b3-badge.done", timeout=120_000, state="attached"
        )
        # Give the UI a moment to finish painting tool_call cards.
        page.wait_for_timeout(1500)
        page.screenshot(path=str(SCREENSHOTS / "02-task-completed.png"), full_page=True)
        print("saved 02-task-completed.png")

        # ── 3. Just the badges + events strip (cropped) ─────────────────
        pipeline = page.locator("section.panel:has-text('pipeline')")
        try:
            pipeline.screenshot(path=str(SCREENSHOTS / "03-pipeline.png"))
            print("saved 03-pipeline.png")
        except Exception as e:
            print(f"pipeline crop failed: {e}")

        # ── 4. Just the Agent live tool calls panel ─────────────────────
        # Multiple panels mention "Agent"; pin to the section whose
        # h2 starts with "Agent — live tool calls".
        agent_panel = page.locator("section.panel:has(h2:has-text('Agent — live tool calls'))")
        try:
            agent_panel.first.screenshot(path=str(SCREENSHOTS / "04-tool-calls.png"))
            print("saved 04-tool-calls.png")
        except Exception as e:
            print(f"agent panel crop failed: {e}")

        # ── 5. Plan + Critique side-by-side (the brains' artefacts) ─────
        plan_panel = page.locator("section.panel:has(h2:has-text('Plan'))")
        try:
            plan_panel.first.screenshot(path=str(SCREENSHOTS / "05-plan.png"))
            print("saved 05-plan.png")
        except Exception as e:
            print(f"plan crop failed: {e}")
        critique_panel = page.locator("section.panel:has(h2:has-text('Critique'))")
        try:
            critique_panel.first.screenshot(path=str(SCREENSHOTS / "06-critique.png"))
            print("saved 06-critique.png")
        except Exception as e:
            print(f"critique crop failed: {e}")

        browser.close()


if __name__ == "__main__":
    main()
