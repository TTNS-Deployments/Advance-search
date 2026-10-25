"""Regenerates the README screenshots from local mode with every sample document indexed.

    .venv/bin/python qa/screenshots.py [query]

Writes imgs/screenshot-search.png (a query with three results) and imgs/screenshot-documents.png.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "tests"))

from live_server import REPO, LiveServer, sign_in  # noqa: E402

QUERY = sys.argv[1] if len(sys.argv) > 1 else "what to do if my laptop is stolen"
OUT = REPO / "imgs"


def main() -> None:
    from playwright.sync_api import sync_playwright

    server = LiveServer(skip=()).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context(viewport={"width": 1280, "height": 1000}, device_scale_factor=1.5,
                                      color_scheme="light", reduced_motion="reduce")
            page = ctx.new_page()
            sign_in(page, server.url, "Admin")
            page.fill("#q", QUERY)
            page.keyboard.press("Enter")
            page.wait_for_selector("#results .result-card")
            page.wait_for_timeout(500)
            page.mouse.move(0, 0)
            height = page.evaluate("document.querySelector('#results').getBoundingClientRect().bottom + 30")
            page.screenshot(path=str(OUT / "screenshot-search.png"), full_page=True, clip={"x": 0, "y": 0, "width": 1280, "height": height})
            page.goto(f"{server.url}/documents")
            page.wait_for_selector("#documents-table tbody tr")
            height = page.evaluate("document.querySelector('#documents-table').getBoundingClientRect().bottom + 30")
            page.screenshot(path=str(OUT / "screenshot-documents.png"), full_page=True, clip={"x": 0, "y": 0, "width": 1280, "height": min(height, 1500)})
            browser.close()
    finally:
        server.stop()
    print(f"Wrote {OUT / 'screenshot-search.png'} and {OUT / 'screenshot-documents.png'}")


if __name__ == "__main__":
    main()
