"""Create upload demo session via API, then screenshot the UI."""
from __future__ import annotations

import json
import subprocess
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "docs" / "assets"
FIXTURE = ROOT / "backend" / "eval" / "fixtures" / "orion_travel_policy.md"
API = "http://127.0.0.1:8000"
UI = "http://127.0.0.1:5173"


def api_json(method: str, path: str, body: dict | None = None, timeout: int = 180) -> dict:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f"{API}{path}",
        method=method,
        data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.loads(res.read())


def main() -> None:
    session = api_json("POST", "/api/sessions", {})
    sid = session["id"]
    print("session", sid)

    up = subprocess.run(
        [
            "curl.exe",
            "-s",
            "-X",
            "POST",
            f"{API}/api/sessions/{sid}/upload",
            "-F",
            f"file=@{FIXTURE};type=text/markdown",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    print("upload", up.stdout[:400])
    upload = json.loads(up.stdout)
    assert upload.get("filename"), upload

    chat = api_json(
        "POST",
        f"/api/sessions/{sid}/chat",
        {
            "message": (
                "According to the attached Orion travel policy, "
                "what is the domestic per diem for metro cities?"
            )
        },
        timeout=180,
    )
    print("domain", chat.get("domain"), "conf", chat.get("confidence"))
    print("reply", (chat.get("reply") or "")[:280])
    sources = [(s.get("source_url"), s.get("title")) for s in (chat.get("sources") or [])[:4]]
    print("sources", sources)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
        page.goto(f"{UI}/#/chat", wait_until="networkidle")
        page.wait_for_timeout(1000)
        page.wait_for_selector(".session-item", timeout=30_000)

        if page.locator(".session-search").count():
            page.fill(".session-search", sid[:8])
            page.wait_for_timeout(400)

        # Prefer an exact match on filtered list (newest session usually first)
        found = False
        rows = page.locator(".session-row")
        for i in range(rows.count()):
            row = rows.nth(i)
            row.locator(".session-item").click()
            page.wait_for_timeout(900)
            if page.locator(".upload-chip").count():
                found = True
                break
        if not found:
            page.locator(".session-item").first.click()
            page.wait_for_timeout(1200)

        page.wait_for_selector(".upload-chip", timeout=30_000)
        page.wait_for_selector(".bubble.assistant", timeout=30_000)
        if page.locator(".session-search").count():
            page.fill(".session-search", "")
            page.wait_for_timeout(300)
        page.screenshot(path=str(ASSETS / "screenshot_upload.png"))
        print("wrote screenshot_upload.png", (ASSETS / "screenshot_upload.png").stat().st_size)

        page.click("button.format-json")
        page.wait_for_selector(".panel", timeout=60_000)
        page.wait_for_timeout(700)
        page.screenshot(path=str(ASSETS / "screenshot_format_json.png"))
        print(
            "wrote screenshot_format_json.png",
            (ASSETS / "screenshot_format_json.png").stat().st_size,
        )
        browser.close()


if __name__ == "__main__":
    main()
