"""Browser tests (IDs match qa/test_cases.md). Local mode: folder storage, SQLite index, mock embeddings."""
from __future__ import annotations

import re

import pytest
import yaml
from live_server import NOT_SEEDED, PASSWORD, REPO, SAMPLES, sign_in

QUERIES = yaml.safe_load((SAMPLES / "queries.yaml").read_text())["queries"]


def search(page, query):
    page.fill("#q", query)
    page.keyboard.press("Enter")
    page.wait_for_selector("#results .result-card, #results .empty-state")
    return page.locator("#results .result-card")


# ---------------------------------------------------------------------------- sign-in and roles

def test_UI01_admin_sign_in_shows_admin_navigation(admin, server):
    nav = admin.locator("nav.main-nav")
    assert nav.get_by_role("link", name="Documents").is_visible()
    assert nav.get_by_role("link", name="Settings").is_visible()
    assert admin.locator(".role-chip").inner_text() == "Admin"
    assert admin.locator("nav.main-nav a[aria-current=page]").inner_text() == "Search"


def test_UI02_user_sign_in_hides_admin_pages(user, server):
    nav = user.locator("nav.main-nav")
    assert nav.get_by_role("link", name="Documents").count() == 0
    assert nav.get_by_role("link", name="Settings").count() == 0
    response = user.goto(f"{server.url}/documents")
    assert response.status == 403
    assert user.get_by_role("heading", name="Not available for your role").is_visible()
    assert user.request.get(f"{server.url}/api/documents").status == 403


def test_UI03_wrong_password_and_sign_out(page, server):
    page.goto(f"{server.url}/auth/login")
    page.check("input[name=role][value=User]")
    page.fill("#password", "not-the-password")
    page.click("button[type=submit]")
    assert page.get_by_role("alert").inner_text().strip().startswith("Wrong password")
    assert page.locator("input[name=role][value=User]").is_checked()  # choice kept
    sign_in(page, server.url, "User")
    page.get_by_role("button", name="Sign out").click()
    page.wait_for_url(re.compile(r".*/auth/login$"))
    page.goto(f"{server.url}/")
    assert "/auth/login" in page.url


def test_UI04_password_reveal_toggle(page, server):
    page.goto(f"{server.url}/auth/login")
    page.fill("#password", "abc")
    reveal = page.get_by_role("button", name="Show password")
    reveal.click()
    assert page.get_attribute("#password", "type") == "text"
    assert page.get_by_role("button", name="Hide password").get_attribute("aria-pressed") == "true"


# ---------------------------------------------------------------------------- documents

def test_UI05_upload_file_and_watch_it_become_indexed(admin, server):
    admin.goto(f"{server.url}/documents")
    admin.set_input_files("#file-input", str(SAMPLES / NOT_SEEDED))
    item = admin.locator(".upload-item").first
    item.locator(".upload-state", has_text="Uploaded").wait_for(timeout=15000)
    assert "Queued for indexing" in item.locator(".upload-msg").inner_text()
    row = admin.locator(f"tr[data-name='{NOT_SEEDED}']")
    row.wait_for(timeout=15000)
    row.locator(".status-chip", has_text="Indexed").wait_for(timeout=20000)  # polling every 3 s
    assert int(row.locator("td.num").nth(1).inner_text()) >= 1
    results = search_after_upload(admin, server)
    assert NOT_SEEDED in results


def search_after_upload(page, server):
    page.goto(f"{server.url}/")
    cards = search(page, "price of a box of A4 paper")
    return [cards.nth(i).locator(".result-title a").inner_text() for i in range(cards.count())]


def test_UI06_upload_validation_messages(admin, server, tmp_path):
    admin.goto(f"{server.url}/documents")
    bad = tmp_path / "notes.txt"
    bad.write_text("plain text")
    fake = tmp_path / "fake.pdf"
    fake.write_bytes(b"MZ not a pdf at all")
    admin.set_input_files("#file-input", [str(bad), str(fake)])
    admin.locator(".upload-item.is-error").nth(1).wait_for(timeout=10000)
    messages = admin.locator(".upload-item .upload-msg").all_inner_texts()
    assert any("Only PDF" in m for m in messages)          # refused in the browser
    assert any("not a valid .pdf" in m for m in messages)  # refused by the server (magic bytes)


def test_UI07_status_chips_and_no_text_document(admin, server):
    admin.goto(f"{server.url}/documents")
    row = admin.locator("tr[data-name='Scanned-Delivery-Note.pdf']")
    assert row.locator(".status-chip").inner_text() == "No text"
    assert "This file may be a scan" in row.locator(".row-error").inner_text()
    assert admin.locator("tr[data-status=indexed]").count() >= 11


def test_UI08_filter_documents(admin, server):
    admin.goto(f"{server.url}/documents")
    admin.select_option("#filter-type", "xlsx")
    admin.wait_for_function("() => [...document.querySelectorAll('#documents-table tbody tr')].every(r => r.dataset.name.endsWith('.xlsx'))")
    admin.select_option("#filter-type", "")
    admin.fill("#filter-q", "leave")
    admin.wait_for_function("() => document.querySelectorAll('#documents-table tbody tr').length === 1")
    assert admin.locator("#documents-table tbody tr").get_attribute("data-name") == "Leave-Policy-2026.pdf"


def test_UI09_delete_needs_confirmation(admin, server):
    name = "Hybrid-Working-Guidelines.docx"
    admin.goto(f"{server.url}/documents")
    row = admin.locator(f"tr[data-name='{name}']")
    row.get_by_role("button", name=f"Delete {name}").click()
    dialog = admin.locator("#confirm-dialog")
    assert dialog.is_visible()
    assert name in dialog.locator("#confirm-message").inner_text()
    dialog.get_by_role("button", name="Cancel").click()
    assert row.is_visible()
    row.get_by_role("button", name=f"Delete {name}").click()
    dialog.get_by_role("button", name="Delete").click()
    admin.locator("#documents-table .alert-success", has_text=f"Deleted {name}").wait_for()
    assert admin.locator(f"tr[data-name='{name}']").count() == 0
    admin.goto(f"{server.url}/")
    titles = search(admin, "can I work from home on Fridays").locator(".result-title a").all_inner_texts()
    assert name not in titles


def test_UI10_reindex_and_sync(admin, server):
    name = "Records-Retention-Schedule.pdf"
    admin.goto(f"{server.url}/documents")
    admin.locator(f"tr[data-name='{name}']").get_by_role("button", name=f"Re-index {name}").click()
    admin.locator("#documents-table .alert-success", has_text="queued for re-indexing").wait_for()
    admin.locator(f"tr[data-name='{name}'] .status-chip", has_text="Indexed").wait_for(timeout=20000)
    admin.get_by_role("button", name="Sync from storage").click()
    admin.locator("#documents-table .alert-success", has_text="Sync from storage").wait_for()


def test_UI11_open_document_streams_original(admin, server):
    admin.goto(f"{server.url}/")
    href = search(admin, "how many days off do I get").first.get_by_role("link", name="Open document").get_attribute("href")
    response = admin.request.get(server.url + href)
    assert response.status == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.body() == (SAMPLES / "Leave-Policy-2026.pdf").read_bytes()
    assert "blob.core.windows.net" not in href and href.startswith("/documents/")


# ---------------------------------------------------------------------------- search

@pytest.mark.parametrize("q", [q for q in QUERIES if q["expected"] not in (NOT_SEEDED, "Hybrid-Working-Guidelines.docx")][:6],
                         ids=lambda q: q["query"][:30])
def test_UI12_queries_return_expected_document_in_top_3(admin, server, q):
    cards = search(admin, q["query"])
    titles = [cards.nth(i).locator(".result-title a").inner_text() for i in range(cards.count())]
    assert 1 <= len(titles) <= 3
    assert q["expected"] in titles


def test_UI13_result_cards_and_match_meter(admin, server):
    cards = search(admin, "approval and budget for laptops")  # a query three documents genuinely match
    assert cards.count() == 3
    summary = admin.locator(".results-summary").inner_text()
    assert re.match(r"3 documents in \d+\.\d s", summary)
    previous = 101
    for i in range(3):
        card = cards.nth(i)
        assert card.locator(".rank").inner_text() == str(i + 1)
        assert card.locator("svg.file-icon").count() == 1
        assert card.locator(".badge").inner_text() in ("PDF", "WORD", "EXCEL")
        assert card.locator(".location-chip").inner_text().strip()
        meter = card.locator("[role=meter]")
        value = int(meter.get_attribute("aria-valuenow"))
        assert card.locator(".match-number").inner_text() == f"{value}%"
        assert value <= previous
        previous = value
        width = card.locator(".meter-fill").evaluate("e => e.getBoundingClientRect().width / e.parentElement.getBoundingClientRect().width")
        assert abs(width * 100 - value) < 2, (width, value)
        colour = card.locator(".meter-fill").evaluate("e => getComputedStyle(e).backgroundColor")
        assert colour.startswith("rgb")
        tip = card.locator(".tooltip").text_content()
        assert "Source: semantic ranker" in tip and "not a probability" in tip
    assert cards.first.locator(".snippet mark").count() >= 1
    assert "Sheet 'Approval limits'" in cards.first.locator(".location-chip").inner_text()


def test_UI14_meter_colour_follows_value(admin, server):
    cards = search(admin, "laptop")  # three documents mention laptops, with clearly different scores
    assert cards.count() >= 2
    colours = [cards.nth(i).locator(".meter-fill").evaluate("e => getComputedStyle(e).backgroundColor") for i in range(cards.count())]
    values = [int(cards.nth(i).locator("[role=meter]").get_attribute("aria-valuenow")) for i in range(cards.count())]
    assert values[0] > values[-1] and colours[0] != colours[-1]


def test_UI15_copy_link_and_match_popover(admin, server):
    cards = search(admin, "battery life of the field tablet")
    cards.first.get_by_role("button", name="Copy link").click()
    admin.locator("#toast", has_text="Link copied").wait_for()
    copied = admin.evaluate("navigator.clipboard.readText()")
    assert copied.startswith(server.url + "/documents/") and copied.endswith(".pdf")
    admin.locator("details.popover summary").click()
    assert admin.locator(".popover-body").is_visible()
    assert "relevance indicator, not a probability" in admin.locator(".popover-body").inner_text()
    admin.keyboard.press("Escape")
    assert not admin.locator(".popover-body").is_visible()


def test_UI16_no_close_match_and_empty_states(admin, server):
    search(admin, "football world cup final score")
    state = admin.locator("#results .empty-state")
    assert state.get_attribute("data-state") == "no-match"
    assert "No matching documents found" in state.inner_text()
    assert state.locator(".tips li").count() == 3


def test_UI17_keyboard_shortcut_examples_and_recent(admin, server):
    admin.locator("body").click(position={"x": 5, "y": 300})
    admin.keyboard.press("/")
    assert admin.evaluate("document.activeElement.id") == "q"
    admin.keyboard.type("hotel limit per night")
    admin.keyboard.press("Enter")
    admin.wait_for_selector("#results .result-card")
    assert "q=hotel+limit+per+night" in admin.url or "q=hotel%20limit%20per%20night" in admin.url
    admin.goto(f"{server.url}/")
    recent = admin.locator("#recent-searches")
    assert recent.is_visible()
    assert "hotel limit per night" in recent.inner_text()
    admin.locator(".chip-row[aria-label='Example searches'] .chip").first.click()
    admin.wait_for_selector("#results .result-card")
    assert admin.input_value("#q") == "how many days off do I get"
    admin.get_by_role("button", name="Clear search").click()
    assert admin.input_value("#q") == ""
    assert admin.locator("#results .result-card").count() == 0


def test_UI18_deep_link_renders_results_without_javascript_request(admin, server):
    admin.goto(f"{server.url}/?q=when+does+the+migration+go+live")
    assert admin.locator("#results .result-card").count() >= 1
    assert admin.locator("#q").input_value() == "when does the migration go live"
    assert admin.locator(".match.is-ready").count() >= 1


def test_UI19_settings_change_number_of_results(admin, server):
    admin.goto(f"{server.url}/settings")
    admin.fill("#top_n", "1")
    admin.get_by_role("button", name="Save settings").click()
    admin.locator(".alert-success").wait_for()
    admin.goto(f"{server.url}/")
    assert search(admin, "annual leave entitlement").count() == 1
    admin.goto(f"{server.url}/settings")
    admin.fill("#top_n", "11")
    admin.get_by_role("button", name="Save settings").click()
    assert "between 1 and 10" in admin.get_by_role("alert").inner_text()
    admin.get_by_role("button", name="Reset to defaults").click()
    admin.locator(".alert-success").wait_for()
    assert admin.input_value("#top_n") == "3"


# ---------------------------------------------------------------------------- look and feel, accessibility

def test_UI20_theme_toggle_persists(admin, server):
    toggle = admin.locator("#theme-toggle")
    before = admin.evaluate("getComputedStyle(document.body).backgroundColor")
    label = toggle.get_attribute("aria-label")
    toggle.click()
    theme = admin.evaluate("document.documentElement.dataset.theme")
    assert theme in ("dark", "light") and label.endswith(f"{theme} theme")
    after = admin.evaluate("getComputedStyle(document.body).backgroundColor")
    assert before != after
    admin.reload()
    assert admin.evaluate("document.documentElement.dataset.theme") == theme
    toggle.click()


@pytest.mark.viewport({"width": 375, "height": 812})
@pytest.mark.parametrize("path,role", [("/auth/login", None), ("/?q=who+approves+a+purchase+over+five+lakh", "User"),
                                       ("/documents", "Admin"), ("/settings", "Admin")])
def test_UI21_no_horizontal_overflow_at_375px(page, server, path, role):
    if role:
        sign_in(page, server.url, role)
    page.goto(server.url + path)
    page.wait_for_load_state("networkidle")
    width = page.evaluate("document.documentElement.scrollWidth")
    assert width <= 375, f"{path}: page is {width}px wide"


@pytest.mark.parametrize("path", ["/auth/login", "/", "/?q=lost+laptop", "/documents", "/settings"])
def test_UI22_accessibility_sanity(page, server, path):
    if path != "/auth/login":
        sign_in(page, server.url, "Admin")
    page.goto(server.url + path)
    problems = page.evaluate("""() => {
      const out = [];
      if (!document.documentElement.lang) out.push('html has no lang');
      if (document.querySelectorAll('h1').length !== 1) out.push('h1 count ' + document.querySelectorAll('h1').length);
      const name = el => (el.getAttribute('aria-label') || el.getAttribute('aria-labelledby') && document.getElementById(el.getAttribute('aria-labelledby'))?.textContent || el.textContent || el.title || '').trim();
      for (const el of document.querySelectorAll('input:not([type=hidden]), select, textarea')) {
        const labelled = (el.id && document.querySelector(`label[for="${el.id}"]`)) || el.closest('label') || el.getAttribute('aria-label');
        if (!labelled) out.push('unlabelled ' + el.outerHTML.slice(0, 80));
      }
      for (const el of document.querySelectorAll('button, a[href]')) {
        if (!el.closest('[hidden]') && !name(el)) out.push('no accessible name ' + el.outerHTML.slice(0, 80));
      }
      for (const el of document.querySelectorAll('svg[role=img]')) if (!el.getAttribute('aria-label')) out.push('svg without label');
      for (const el of document.querySelectorAll('svg:not([role])')) if (el.getAttribute('aria-hidden') !== 'true') out.push('decorative svg not hidden');
      const ids = [...document.querySelectorAll('[id]')].map(e => e.id);
      const dupes = ids.filter((id, i) => ids.indexOf(id) !== i);
      if (dupes.length) out.push('duplicate ids ' + dupes);
      return out;
    }""")
    assert not problems, problems


def test_UI23_focus_order_and_visible_focus(admin, server):
    admin.goto(f"{server.url}/documents")
    admin.evaluate("document.activeElement.blur()")
    order = []
    for _ in range(6):
        admin.keyboard.press("Tab")
        order.append(admin.evaluate("""() => { const e = document.activeElement;
            return (e.textContent || e.getAttribute('aria-label') || e.id).trim().slice(0, 30); }"""))
        ring = admin.evaluate("getComputedStyle(document.activeElement).boxShadow")
        assert ring != "none", f"no visible focus on {order[-1]}"
    assert order[:5] == ["Skip to content", "AdvanceSearch", "Search", "Documents", "Settings"], order


def test_UI24_reduced_motion_respected(admin, server):
    cards = search(admin, "battery life of the field tablet")
    duration = cards.first.locator(".meter-fill").evaluate("e => getComputedStyle(e).transitionDuration")
    assert float(duration.rstrip("ms").split(",")[0]) < 0.01


def test_UI25_security_headers_on_pages(admin, server):
    response = admin.goto(f"{server.url}/")
    csp = response.headers["content-security-policy"]
    assert "script-src 'self'" in csp and "unsafe-inline" not in csp
    assert response.headers["x-frame-options"] == "DENY"
    assert (REPO / "Code/webapp/static/vendor/htmx-2.0.4.min.js").is_file()
    assert PASSWORD not in admin.content()
