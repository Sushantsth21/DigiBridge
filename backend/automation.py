import base64
import logging
import os
from datetime import datetime

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

log = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Portal Registry  (Feature #5)
# Each entry maps portal name → automation function
# ──────────────────────────────────────────────
BASE_URL = os.getenv("PORTAL_BASE_URL", "http://localhost:8080")

PORTAL_REGISTRY: dict[str, callable] = {}


def register_portal(name: str):
    """Decorator to register a portal automation function."""
    def decorator(fn):
        PORTAL_REGISTRY[name] = fn
        log.info(f"Registered portal: {name}")
        return fn
    return decorator


def run_automation(intent: dict, portal: str = "hospital") -> str:
    """
    Dispatch to the correct portal automation.
    Returns Base64-encoded PNG screenshot of success state.
    """
    fn = PORTAL_REGISTRY.get(portal)
    if not fn:
        available = list(PORTAL_REGISTRY.keys())
        raise ValueError(f"Unknown portal '{portal}'. Available: {available}")

    log.info(f"Running automation for portal='{portal}' intent={intent}")
    return fn(intent)


# ──────────────────────────────────────────────
# Shared Playwright helpers
# ──────────────────────────────────────────────
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


def _safe_fill(page, selector: str, value: str, timeout: int = 5000):
    try:
        page.wait_for_selector(selector, timeout=timeout)
        page.fill(selector, value)
        log.info(f"Filled '{selector}' with '{value}'")
    except PlaywrightTimeout:
        log.warning(f"Selector '{selector}' not found — skipping fill")


def _safe_click(page, selector: str, timeout: int = 5000):
    try:
        page.wait_for_selector(selector, timeout=timeout)
        page.click(selector)
        log.info(f"Clicked '{selector}'")
    except PlaywrightTimeout:
        log.warning(f"Selector '{selector}' not found — skipping click")


# ──────────────────────────────────────────────
# Portal: Hospital  (original)
# ──────────────────────────────────────────────
@register_portal("hospital")
def automate_hospital(intent: dict) -> str:
    doctor = intent.get("doctor", "")
    date_str = intent.get("date", datetime.today().strftime("%Y-%m-%d"))
    action = intent.get("action", "schedule")

    with sync_playwright() as p:
        browser = _launch_browser(p)
        page = browser.new_page()

        log.info(f"Hospital portal → navigating to {BASE_URL}/dummy_portal/")
        page.goto(f"{BASE_URL}/dummy_portal/", wait_until="domcontentloaded")

        # Login bypass (hardcoded for hackathon)
        _safe_click(page, "#login-btn")
        page.wait_for_timeout(500)

        if action == "schedule":
            _safe_fill(page, "#doctor-input", doctor)
            _safe_fill(page, "#date-input", date_str)
            _safe_click(page, "#submit-btn")

            # Wait for success page
            try:
                page.wait_for_url("**/success**", timeout=5000)
            except PlaywrightTimeout:
                log.warning("Success URL not reached — taking screenshot anyway")

        screenshot = _screenshot_b64(page)
        browser.close()

    log.info("Hospital automation complete")
    return screenshot


# ──────────────────────────────────────────────
# Portal: Pharmacy  (Feature #5 — new)
# ──────────────────────────────────────────────
@register_portal("pharmacy")
def automate_pharmacy(intent: dict) -> str:
    medication = intent.get("medication", "")
    quantity = intent.get("quantity", "30")
    action = intent.get("action", "refill")

    with sync_playwright() as p:
        browser = _launch_browser(p)
        page = browser.new_page()

        log.info(f"Pharmacy portal → navigating to {BASE_URL}/dummy_portal/pharmacy/")
        page.goto(f"{BASE_URL}/dummy_portal/pharmacy/", wait_until="domcontentloaded")

        if action == "refill":
            _safe_fill(page, "#medication-input", medication)
            _safe_fill(page, "#quantity-input", quantity)
            _safe_click(page, "#refill-btn")

            try:
                page.wait_for_url("**/success**", timeout=5000)
            except PlaywrightTimeout:
                log.warning("Pharmacy success URL not reached — taking screenshot")

        screenshot = _screenshot_b64(page)
        browser.close()

    log.info("Pharmacy automation complete")
    return screenshot


# ──────────────────────────────────────────────
# Portal: Utility  (Feature #5 — new)
# ──────────────────────────────────────────────
@register_portal("utility")
def automate_utility(intent: dict) -> str:
    amount = intent.get("amount", "")
    action = intent.get("action", "pay_bill")

    with sync_playwright() as p:
        browser = _launch_browser(p)
        page = browser.new_page()

        log.info(f"Utility portal → navigating to {BASE_URL}/dummy_portal/utility/")
        page.goto(f"{BASE_URL}/dummy_portal/utility/", wait_until="domcontentloaded")

        if action == "pay_bill":
            if amount:
                _safe_fill(page, "#amount-input", amount)
            _safe_click(page, "#pay-btn")

            try:
                page.wait_for_url("**/success**", timeout=5000)
            except PlaywrightTimeout:
                log.warning("Utility success URL not reached — taking screenshot")

        screenshot = _screenshot_b64(page)
        browser.close()

    log.info("Utility automation complete")
    return screenshot
