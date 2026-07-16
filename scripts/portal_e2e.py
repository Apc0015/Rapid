"""End-to-end browser validation for the unified desktop and mobile portal."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

AXE_PATH = Path(__file__).resolve().parents[1] / "frontend" / "node_modules" / "axe-core" / "axe.min.js"


def assert_accessible(page, label: str) -> None:
    if not AXE_PATH.exists():
        raise AssertionError(f"axe-core is missing at {AXE_PATH}")
    page.add_script_tag(path=str(AXE_PATH))
    result = page.evaluate(
        """async () => axe.run(document, {
          runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'] }
        })"""
    )
    violations = [item for item in result["violations"] if item.get("impact") in {"serious", "critical"}]
    if violations:
        details = "; ".join(
            f"{item['id']}: {len(item['nodes'])} node(s), examples "
            + ", ".join(str(node["target"]) for node in item["nodes"][:4])
            for item in violations
        )
        raise AssertionError(f"Accessibility violations on {label}: {details}")


def run(base_url: str, output: Path, api_url: str = "") -> None:
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        desktop_context = browser.new_context(viewport={"width": 1440, "height": 1000}, bypass_csp=True)
        desktop = desktop_context.new_page()
        if api_url:
            desktop.add_init_script(f"window.RAPID_API_URL = {json.dumps(api_url)};")
        errors: list[str] = []
        desktop.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        desktop.on("pageerror", lambda error: errors.append(str(error)))
        desktop.goto(f"{base_url}/login", wait_until="domcontentloaded")
        desktop.wait_for_selector("#login-form")
        assert_accessible(desktop, "login")
        desktop.screenshot(path=str(output / "desktop-login.png"), full_page=True)
        desktop.click("#demo-button")
        desktop.wait_for_url("**/workspace/overview")
        desktop.wait_for_selector("#organization-name")
        assert desktop.locator("#organization-name").inner_text() == "Northstar Labs"
        assert desktop.locator(".portal-nav [data-view]").count() == 12
        assert desktop.locator("#root").get_attribute("data-reactroot") is None
        desktop.fill("#intelligence-question", "Tell me about the organization")
        desktop.click(".intelligence-submit")
        desktop.wait_for_selector(".intelligence-response")
        organization_brief = desktop.locator(".intelligence-response").inner_text().lower()
        assert "northstar labs" in organization_brief
        assert "live ai analysis" not in organization_brief
        desktop.click('.portal-nav [data-view="actions"]')
        desktop.wait_for_function(
            "document.querySelector('#intelligence-question')?.getAttribute('placeholder') === 'Ask about commitments and owners'"
        )
        assert desktop.locator(".intelligence-response").count() == 0
        assert desktop.locator("#intelligence-question").get_attribute("placeholder") == "Ask about commitments and owners"
        desktop.fill("#intelligence-question", "What needs attention today?")
        desktop.click(".intelligence-submit")
        desktop.wait_for_selector(".intelligence-response")
        assert "open commitments" in desktop.locator(".intelligence-response").inner_text().lower()
        desktop.click('.portal-nav [data-view="overview"]')
        assert_accessible(desktop, "workspace overview")
        desktop.screenshot(path=str(output / "desktop-overview.png"), full_page=True)

        expected = {"people": 12, "crm": 6, "projects": 3, "tickets": 3, "departments": 10}
        selectors = {"people": "#people-table tr", "crm": "#crm-list .entity-card", "projects": "#projects-list .entity-card", "tickets": "#tickets-table tr", "departments": "#departments-list .department-card"}
        for view, count in expected.items():
            desktop.click(f'.portal-nav [data-view="{view}"]')
            desktop.locator(selectors[view]).nth(count - 1).wait_for()
            assert desktop.locator(selectors[view]).count() == count, view
        desktop.click('.portal-nav [data-view="projects"]')
        desktop.click("#create-project")
        desktop.wait_for_function("document.querySelector('#create-project-dialog').open === true")
        desktop.locator("#create-project-dialog").get_by_role("button", name="Close dialog").click()

        desktop.click('.portal-nav [data-view="meetings"]')
        desktop.locator("#meetings-list [data-meeting]").first.click()
        desktop.wait_for_function("document.querySelector('#meeting-dialog').open === true")
        desktop.fill("#meeting-notes", "E2E validation note")
        desktop.fill("#meeting-decisions", "E2E decision recorded")
        desktop.select_option("#meeting-recurrence", "biweekly")
        desktop.click('#meeting-edit-form button[type="submit"]')
        desktop.wait_for_function("document.querySelector('#meeting-dialog').open === false")
        desktop.locator("#meetings-list [data-meeting]").first.click()
        desktop.wait_for_function("document.querySelector('#meeting-dialog').open === true")
        assert desktop.locator("#meeting-notes").input_value() == "E2E validation note"
        assert desktop.locator("#meeting-decisions").input_value() == "E2E decision recorded"
        desktop.locator("#meeting-dialog").get_by_role("button", name="Close dialog").click()
        desktop.click('.portal-nav [data-view="reports"]')
        desktop.select_option("#report-department", "sales")
        desktop.click("#generate-report")
        desktop.wait_for_selector("#report-output .report-metrics")
        desktop.click('.portal-nav [data-view="library"]')
        desktop.wait_for_selector("#library-search-form")
        desktop.wait_for_selector('[data-portal-view="library"] .library-layout')
        assert_accessible(desktop, "organization library")
        desktop.screenshot(path=str(output / "desktop-library.png"), full_page=True)
        desktop.click('.portal-nav [data-view="search"]')
        desktop.fill("#global-search-input", "Atlas")
        desktop.click('#global-search-form button[type="submit"]')
        desktop.wait_for_selector("#search-results .search-result")
        assert desktop.locator("#search-results .search-result").count() >= 4
        desktop.click('.portal-nav [data-view="notifications"]')
        desktop.locator("#notifications-list .notification-row").nth(3).wait_for()
        assert desktop.locator("#notifications-list .notification-row").count() == 4
        desktop.click('.product-sidebar-footer [data-view="settings"]')
        desktop.wait_for_selector("#settings-runtime article")
        assert desktop.locator("#settings-runtime article").count() >= 6
        assert desktop.locator("#settings-runtime").inner_text().lower().find("ready") >= 0
        desktop.screenshot(path=str(output / "desktop-settings.png"), full_page=True)

        desktop.goto(f"{base_url}/admin/configuration", wait_until="domcontentloaded")
        desktop.wait_for_selector("#features-list .admin-card")
        assert desktop.locator("#features-list .admin-card").count() >= 8
        assert desktop.locator("#models-list .admin-card").count() == 2
        assert desktop.locator("#connections-list .connection-row").count() >= 4
        assert_accessible(desktop, "tenant configuration")
        desktop.screenshot(path=str(output / "desktop-admin.png"), full_page=True)

        desktop.goto(f"{base_url}/operations", wait_until="domcontentloaded")
        desktop.wait_for_selector(".department-tabs button")
        assert desktop.locator(".department-tabs button").count() == 10
        assert desktop.locator(".operations-metrics article").count() == 4
        assert desktop.locator(".operations-data").is_visible()
        assert_accessible(desktop, "operations console")
        desktop.screenshot(path=str(output / "desktop-operations.png"), full_page=True)

        token = desktop.evaluate("localStorage.getItem('rapid_people_ops_token')")
        profile = desktop.evaluate("localStorage.getItem('rapid_profile')")
        mobile_context = browser.new_context(viewport={"width": 390, "height": 844}, bypass_csp=True)
        mobile = mobile_context.new_page()
        if api_url:
            mobile.add_init_script(f"window.RAPID_API_URL = {json.dumps(api_url)};")
        mobile.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        mobile.on("pageerror", lambda error: errors.append(str(error)))
        mobile.goto(f"{base_url}/login", wait_until="domcontentloaded")
        mobile.evaluate("([token, profile]) => { localStorage.setItem('rapid_people_ops_token', token); localStorage.setItem('rapid_profile', profile); }", [token, profile])
        mobile.goto(f"{base_url}/workspace/overview", wait_until="domcontentloaded")
        mobile.wait_for_selector("#organization-name")
        mobile.click("#open-navigation")
        mobile.wait_for_timeout(300)
        sidebar = mobile.locator("#portal-sidebar").bounding_box()
        assert sidebar and sidebar["x"] == 0 and sidebar["width"] >= 280
        mobile.screenshot(path=str(output / "mobile-navigation.png"))
        mobile.click('.portal-nav [data-view="people"]')
        mobile.wait_for_timeout(300)
        assert not mobile.locator("#portal-sidebar").evaluate("node => node.classList.contains('open')")
        assert mobile.locator("#people-table tr").count() == 12
        overflow = mobile.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        assert overflow <= 1, f"mobile horizontal overflow: {overflow}px"
        assert_accessible(mobile, "mobile people directory")
        mobile.screenshot(path=str(output / "mobile-people.png"), full_page=True)
        mobile.goto(f"{base_url}/admin/configuration", wait_until="domcontentloaded")
        mobile.wait_for_selector("#features-list .admin-card")
        mobile.locator(".mobile-topbar button[aria-label='Open navigation']").click()
        mobile.wait_for_timeout(300)
        admin_sidebar = mobile.locator(".admin-shell .portal-sidebar").bounding_box()
        assert admin_sidebar and admin_sidebar["x"] == 0 and admin_sidebar["width"] >= 280
        mobile.screenshot(path=str(output / "mobile-admin-navigation.png"))
        mobile.locator(".admin-shell .portal-nav a", has_text="Users and access").click()
        mobile.wait_for_url("**/admin/users")
        mobile.wait_for_selector("#invite-form")
        overflow = mobile.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        assert overflow <= 1, f"mobile admin horizontal overflow: {overflow}px"
        assert_accessible(mobile, "mobile administration")
        mobile.screenshot(path=str(output / "mobile-admin-users.png"), full_page=True)

        tablet_context = browser.new_context(viewport={"width": 924, "height": 980}, bypass_csp=True)
        tablet = tablet_context.new_page()
        if api_url:
            tablet.add_init_script(f"window.RAPID_API_URL = {json.dumps(api_url)};")
        tablet.goto(f"{base_url}/login", wait_until="domcontentloaded")
        tablet.evaluate("([token, profile]) => { localStorage.setItem('rapid_people_ops_token', token); localStorage.setItem('rapid_profile', profile); }", [token, profile])
        tablet.goto(f"{base_url}/workspace/overview", wait_until="domcontentloaded")
        tablet.wait_for_selector("#portal-sidebar")
        sidebar = tablet.locator("#portal-sidebar").bounding_box()
        assert sidebar and sidebar["x"] == 0 and sidebar["width"] >= 220
        assert not tablet.locator("#portal-sidebar .mobile-only.icon-only").is_visible()
        overflow = tablet.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        assert overflow <= 1, f"tablet horizontal overflow: {overflow}px"
        assert_accessible(tablet, "tablet workspace overview")
        tablet.screenshot(path=str(output / "tablet-overview.png"), full_page=True)
        tablet.close()

        desktop.goto(f"{base_url}/workspace/overview", wait_until="domcontentloaded")
        desktop.wait_for_selector("#reset-demo")
        desktop.once("dialog", lambda dialog: dialog.accept())
        desktop.click("#reset-demo")
        desktop.wait_for_timeout(500)
        browser.close()
        if errors:
            raise AssertionError(f"Browser errors: {errors}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:4173")
    parser.add_argument("--output", type=Path, default=Path("/tmp/rapid-portal-e2e"))
    parser.add_argument("--api-url", default="")
    arguments = parser.parse_args()
    run(arguments.base_url.rstrip("/"), arguments.output, arguments.api_url.rstrip("/"))
    print(f"Portal E2E passed. Screenshots: {arguments.output}")
