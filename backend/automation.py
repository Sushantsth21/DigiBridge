import base64
import logging
import os
from datetime import datetime
from typing import Callable

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

log = logging.getLogger(__name__)

BASE_URL = os.getenv("PORTAL_BASE_URL", "http://dummy-portal")

StepCallback = Callable[[str, str], None]
PORTAL_REGISTRY: dict[str, callable] = {}


def register_portal(name: str):
    def decorator(fn):
        PORTAL_REGISTRY[name] = fn
        return fn

    return decorator


def _step(cb: StepCallback | None, step: str, detail: str = ""):
    if cb:
        try:
            cb(step, detail)
        except Exception:
            pass


def _launch_browser(playwright):
    return playwright.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
        ],
    )


def _screenshot_b64(page) -> str:
    png = page.screenshot(full_page=False)
    return base64.b64encode(png).decode("utf-8")


def _candidate_urls(portal: str) -> list[str]:
    base = BASE_URL.rstrip("/")
    urls = [
        f"{base}/",
        f"{base}/index.html",
        f"{base}/{portal}/",
        f"{base}/{portal}/index.html",
        f"{base}/dummy_portal/",
        f"{base}/dummy_portal/index.html",
        f"{base}/dummy_portal/{portal}/",
        f"{base}/dummy_portal/{portal}/index.html",
    ]

    # Add common local/container alternates.
    if "dummy-portal" in base:
        alt = base.replace("dummy-portal", "localhost:8080")
        urls += [f"{alt}/{portal}/", f"{alt}/dummy_portal/{portal}/"]
    if "localhost:8080" in base:
        alt = base.replace("localhost:8080", "dummy-portal")
        urls += [f"{alt}/{portal}/", f"{alt}/dummy_portal/{portal}/"]

    deduped: list[str] = []
    seen: set[str] = set()
    for u in urls:
        if u not in seen:
            deduped.append(u)
            seen.add(u)
    return deduped


def _goto_portal(page, portal: str, required_selector: str, cb: StepCallback | None):
    last_error = None
    for url in _candidate_urls(portal):
        try:
            _step(cb, "🌐 Opening portal page…", url)
            page.goto(url, wait_until="domcontentloaded", timeout=9000)
            if page.query_selector(required_selector) is None:
                log.warning("Missing required selector '%s' at %s", required_selector, url)
                continue
            return
        except Exception as e:
            last_error = e
            log.warning("Portal open failed at %s: %s", url, e)
    raise RuntimeError(f"Unable to reach working page for portal '{portal}'") from last_error


def _must_fill(page, selector: str, value: str, cb: StepCallback | None, label: str):
    _step(cb, f"✍️ Filling {label}…", value)
    page.wait_for_selector(selector, timeout=7000)
    page.fill(selector, value)


def _must_click(page, selector: str, cb: StepCallback | None, label: str):
    _step(cb, f"🖱️ Clicking {label}…")
    page.wait_for_selector(selector, timeout=7000)
    page.click(selector)


def run_automation(intent: dict, portal: str = "hospital", step_callback: StepCallback | None = None) -> str:
    fn = PORTAL_REGISTRY.get(portal)
    if not fn:
        raise ValueError(f"Unknown portal '{portal}'. Available: {list(PORTAL_REGISTRY.keys())}")
    return fn(intent, step_callback)


def validate_portal_profile(portal: str) -> dict:
    required_by_portal = {
        "hospital": "#submit-btn",
        "pharmacy": "#refill-btn",
        "utility": "#pay-btn",
    }
    if portal not in required_by_portal:
        raise ValueError(f"Unknown portal '{portal}'. Available: {list(required_by_portal.keys())}")

    required = required_by_portal[portal]
    reached = None
    last_error = None

    with sync_playwright() as p:
        browser = _launch_browser(p)
        page = browser.new_page()

        for url in _candidate_urls(portal):
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=8000)
                if page.query_selector(required):
                    reached = url
                    break
                last_error = f"selector {required} missing at {url}"
            except Exception as e:
                last_error = str(e)

        screenshot_b64 = _screenshot_b64(page)
        browser.close()

    return {
        "portal": portal,
        "base_url": BASE_URL,
        "candidate_urls": _candidate_urls(portal),
        "reachable": reached is not None,
        "reached_url": reached,
        "missing_selectors": [] if reached else [required],
        "last_error": last_error,
        "screenshot_b64": screenshot_b64,
    }


@register_portal("hospital")
def automate_hospital(intent: dict, cb: StepCallback | None = None) -> str:
    doctor = intent.get("doctor", "smith")
    date_str = intent.get("date", datetime.today().strftime("%Y-%m-%d"))

    with sync_playwright() as p:
        browser = _launch_browser(p)
        page = browser.new_page()

        _goto_portal(page, "hospital", "#submit-btn", cb)
        _must_click(page, "#login-btn", cb, "Sign In")
        page.wait_for_timeout(250)

        _must_fill(page, "#doctor-input", doctor, cb, "doctor")
        _must_fill(page, "#date-input", date_str, cb, "date")
        _must_click(page, "#submit-btn", cb, "Submit Request")

        _step(cb, "⏳ Waiting for confirmation page…")
        try:
            page.wait_for_url("**/success**", timeout=7000)
        except PlaywrightTimeout:
            log.warning("Hospital success page did not load in time")

        screenshot = _screenshot_b64(page)
        browser.close()

    _step(cb, "✅ Hospital task complete")
    return screenshot


@register_portal("pharmacy")
def automate_pharmacy(intent: dict, cb: StepCallback | None = None) -> str:
    medication = intent.get("medication", "lisinopril")
    quantity = str(intent.get("quantity", "90"))

    with sync_playwright() as p:
        browser = _launch_browser(p)
        page = browser.new_page()

        _goto_portal(page, "pharmacy", "#refill-btn", cb)
        _must_fill(page, "#medication-input", medication, cb, "medication")
        _must_fill(page, "#quantity-input", quantity, cb, "days supply")
        _must_click(page, "#refill-btn", cb, "Submit Refill")

        _step(cb, "⏳ Waiting for confirmation page…")
        try:
            page.wait_for_url("**/success**", timeout=7000)
        except PlaywrightTimeout:
            log.warning("Pharmacy success page did not load in time")

        screenshot = _screenshot_b64(page)
        browser.close()

    _step(cb, "✅ Pharmacy task complete")
    return screenshot


@register_portal("utility")
def automate_utility(intent: dict, cb: StepCallback | None = None) -> str:
    amount = str(intent.get("amount", "142.50"))

    with sync_playwright() as p:
        browser = _launch_browser(p)
        page = browser.new_page()

        _goto_portal(page, "utility", "#pay-btn", cb)
        _must_fill(page, "#amount-input", amount, cb, "amount")
        _must_click(page, "#pay-btn", cb, "Submit Payment")

        _step(cb, "⏳ Waiting for confirmation page…")
        try:
            page.wait_for_url("**/success**", timeout=7000)
        except PlaywrightTimeout:
            log.warning("Utility success page did not load in time")

        screenshot = _screenshot_b64(page)
        browser.close()

    _step(cb, "✅ Utility task complete")
    return screenshot
