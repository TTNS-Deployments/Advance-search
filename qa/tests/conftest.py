"""Shared fixtures for the browser tests (Playwright, headless Chromium) against a live local-mode server.

    .venv/bin/python -m playwright install --with-deps chromium     # once
    .venv/bin/python -m pytest qa/tests -v
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from live_server import LiveServer, sign_in  # noqa: E402


@pytest.fixture(scope="session")
def server():
    srv = LiveServer().start()
    yield srv
    srv.stop()


@pytest.fixture(scope="session")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


class ConsoleWatcher:
    """Collects JavaScript errors, warnings (including CSP violations) and failed loads. 4xx responses the tests
    ask for on purpose (a wrong password, a refused upload) are application answers, not page errors."""

    EXPECTED = re.compile(r"Failed to load resource: the server responded with a status of 4\d\d")

    def __init__(self, page):
        self.messages: list[str] = []
        page.on("console", self._console)
        page.on("pageerror", lambda e: self.messages.append(f"pageerror: {e}"))

    def _console(self, message):
        if message.type in ("error", "warning") and not self.EXPECTED.search(message.text):
            self.messages.append(f"{message.type}: {message.text}")


@pytest.fixture
def context(browser, request):
    marker = request.node.get_closest_marker("viewport")
    viewport = marker.args[0] if marker else {"width": 1280, "height": 900}
    ctx = browser.new_context(viewport=viewport, reduced_motion="reduce")
    ctx.grant_permissions(["clipboard-read", "clipboard-write"])
    yield ctx
    ctx.close()


@pytest.fixture
def page(context):
    pg = context.new_page()
    pg.console = ConsoleWatcher(pg)
    yield pg
    assert not pg.console.messages, pg.console.messages  # no console errors on any page a test visited


@pytest.fixture
def admin(page, server):
    sign_in(page, server.url, "Admin")
    return page


@pytest.fixture
def user(page, server):
    sign_in(page, server.url, "User")
    return page


def pytest_configure(config):
    config.addinivalue_line("markers", "viewport(size): browser viewport for the test")
