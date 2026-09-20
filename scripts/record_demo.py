"""Record a silent Prism demo walkthrough for later voiceover.

Uses the live UI at http://localhost:5173. Follows docs/demo_script.md.

    python scripts/record_demo.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import Locator, Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
UI = "http://localhost:5173"
API = "http://127.0.0.1:8000"
FIXTURE = ROOT / "backend" / "eval" / "fixtures" / "orion_travel_policy.md"
OUT_DIR = ROOT / "docs" / "assets" / "_demo_record"
ANSWER_MS = 180_000
FFMPEG = Path(
    r"C:\Users\dania\AppData\Local\Programs\Python\Python311\Lib\site-packages"
    r"\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe"
)
RECORD_SIZE = (1920, 1080)


def _browser(p, width: int, height: int):
    args = [
        "--window-position=0,0",
        f"--window-size={width},{height}",
        "--force-device-scale-factor=1",
        "--high-dpi-support=1",
        "--disable-infobars",
    ]
    try:
        return p.chromium.launch(channel="chrome", headless=False, args=args)
    except Exception:
        return p.chromium.launch(headless=False, args=args)


def hold(page: Page, ms: int) -> None:
    page.wait_for_timeout(ms)


def api(method: str, path: str, token: str | None = None, body: dict | None = None):
    req = urllib.request.Request(
        f"{API}{path}",
        data=None if body is None else json.dumps(body).encode(),
        method=method,
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
        if not raw:
            return None
        return json.loads(raw)


def clear_alex_sessions() -> None:
    auth = api(
        "POST",
        "/api/auth/login",
        body={"email": "alex.employee@prism.local", "password": "Prism2026!"},
    )
    token = auth["token"]
    sessions = api("GET", "/api/sessions", token=token) or []
    for row in sessions:
        sid = row.get("id")
        if sid:
            try:
                api("DELETE", f"/api/sessions/{sid}", token=token)
            except urllib.error.HTTPError:
                pass


def warmup_models() -> None:
    for model, prompt in (
        ("qwen2.5:7b-instruct", "Reply with the single word ready."),
        ("qwen2.5:3b-instruct", "Expense claim approval"),
    ):
        body = json.dumps(
            {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "keep_alive": "25m",
                "options": {"num_predict": 8},
            }
        ).encode()
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/generate",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            resp.read()


def inject_chrome(page: Page) -> None:
    page.evaluate(
        """() => {
          const old = document.getElementById('prism-demo-caption');
          if (old) old.remove();
          if (document.getElementById('prism-demo-style')) return;
          const style = document.createElement('style');
          style.id = 'prism-demo-style';
          style.textContent = `
            html, body, #root, .app, .landing, .main, .login-page {
              overflow: hidden !important;
              height: 100% !important;
              max-width: none !important;
              width: 100% !important;
            }
            * { scrollbar-width: none !important; }
            *::-webkit-scrollbar { width: 0 !important; height: 0 !important; display: none !important; }
            .landing { overflow: hidden !important; height: 100% !important; padding-top: 1rem; }
            .messages { scroll-behavior: auto; overflow-y: auto; }
            .composer-shell { padding: 0.85rem 1.5rem 1.2rem !important; }
            .bubble { animation: prismIn 0.35s ease; }
            @keyframes prismIn {
              from { opacity: 0; transform: translateY(6px); }
              to { opacity: 1; transform: none; }
            }
          `;
          document.head.appendChild(style);
        }"""
    )


def smooth_scroll(page: Page, selector: str, duration_ms: int = 900) -> None:
    page.evaluate(
        """async ({ selector, duration }) => {
          const el = document.querySelector(selector);
          if (!el) return;
          const root = el.closest('.messages') || document.scrollingElement;
          if (!root) return;
          const from = root.scrollTop;
          const top = el.getBoundingClientRect().top - root.getBoundingClientRect().top + root.scrollTop;
          const to = Math.max(0, top - 28);
          const dist = to - from;
          if (Math.abs(dist) < 8) return;
          await new Promise((resolve) => {
            const t0 = performance.now();
            const tick = (now) => {
              const p = Math.min(1, (now - t0) / duration);
              const ease = 1 - Math.pow(1 - p, 3);
              root.scrollTop = from + dist * ease;
              if (p < 1) requestAnimationFrame(tick);
              else resolve();
            };
            requestAnimationFrame(tick);
          });
        }""",
        {"selector": selector, "duration": duration_ms},
    )


def smooth_window(page: Page, y: int, duration_ms: int = 1100) -> None:
    page.evaluate(
        """async ({ y, duration }) => {
          const root = document.scrollingElement;
          if (!root) return;
          const from = root.scrollTop;
          const dist = y - from;
          if (Math.abs(dist) < 8) return;
          await new Promise((resolve) => {
            const t0 = performance.now();
            const tick = (now) => {
              const p = Math.min(1, (now - t0) / duration);
              const ease = 1 - Math.pow(1 - p, 3);
              root.scrollTop = from + dist * ease;
              if (p < 1) requestAnimationFrame(tick);
              else resolve();
            };
            requestAnimationFrame(tick);
          });
        }""",
        {"y": y, "duration": duration_ms},
    )


def human_click(page: Page, locator: Locator) -> None:
    locator.wait_for(state="visible")
    box = locator.bounding_box()
    if box:
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=16)
        hold(page, 220)
    locator.click()


def wait_ready(page: Page) -> None:
    page.wait_for_function(
        """() => {
          const b = document.querySelector('button.send');
          return b && b.textContent.trim() === 'Send';
        }""",
        timeout=ANSWER_MS,
    )


def wait_title(page: Page, timeout_ms: int = 12000) -> None:
    try:
        page.wait_for_function(
            """() => {
              const h = document.querySelector('.topbar h1');
              const t = (h && h.textContent || '').trim();
              if (!t) return false;
              const bad = /^(New conversation|Ask across five domains|Untitled chat)$/i;
              return !bad.test(t) && !/^actually\\b/i.test(t);
            }""",
            timeout=timeout_ms,
        )
    except Exception:
        pass
    hold(page, 900)


def type_and_send(page: Page, text: str, hold_ms: int = 5500) -> None:
    before = page.locator(".bubble.assistant").count()
    users_before = page.locator(".bubble.user").count()
    box = page.locator("textarea")
    box.scroll_into_view_if_needed()
    human_click(page, box)
    box.fill("")
    hold(page, 400)
    box.press_sequentially(text, delay=58)
    hold(page, 1400)
    human_click(page, page.locator("button.send"))
    page.wait_for_function(
        f"() => document.querySelectorAll('.bubble.user').length > {users_before}",
        timeout=15_000,
    )
    user = page.locator(".bubble.user").last
    user.scroll_into_view_if_needed()
    hold(page, 2000)
    page.wait_for_function(
        f"() => document.querySelectorAll('.bubble.assistant').length > {before}",
        timeout=ANSWER_MS,
    )
    wait_ready(page)
    hold(page, 400)
    last = page.locator(".bubble.assistant").last
    last.scroll_into_view_if_needed()
    wait_title(page)
    hold(page, hold_ms)


def click_format(page: Page, name: str, hold_ms: int = 3800) -> None:
    btn = page.get_by_role("button", name=name, exact=True)
    human_click(page, btn)
    if name != "Excel":
        page.wait_for_selector(".format-panel")
    wait_ready(page)
    hold(page, 250)
    if page.locator(".format-panel").count():
        smooth_scroll(page, ".format-panel", 800)
    hold(page, hold_ms)


def run() -> Path:
    if not FIXTURE.exists():
        raise SystemExit(f"missing fixture {FIXTURE}")
    print("warming models and clearing leftover chats…")
    warmup_models()
    clear_alex_sessions()
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        width, height = RECORD_SIZE
        print(f"recording 16:9 {width}x{height} (fixed window, no maximize, no letterbox)")
        browser = _browser(p, width, height)
        context = browser.new_context(
            viewport={"width": width, "height": height},
            screen={"width": width, "height": height},
            device_scale_factor=1,
            record_video_dir=str(OUT_DIR),
            record_video_size={"width": width, "height": height},
            accept_downloads=True,
        )
        page = context.new_page()
        page.goto(UI, wait_until="networkidle")
        metrics = page.evaluate(
            """() => {
              const login = document.querySelector('.login-page');
              const r = login && login.getBoundingClientRect();
              return {
                inner: [window.innerWidth, window.innerHeight],
                login: r ? [Math.round(r.width), Math.round(r.height), Math.round(r.x)] : null,
              };
            }"""
        )
        print(f"page inner {metrics['inner']} login {metrics['login']}")
        inject_chrome(page)
        hold(page, 18000)

        page.get_by_text("Alex Rao").first.wait_for()
        hold(page, 2500)
        human_click(page, page.get_by_role("button", name="Sign in"))
        page.get_by_role("heading", name="One query, any format.").wait_for()
        inject_chrome(page)
        hold(page, 24000)

        human_click(page, page.get_by_role("button", name="Try the live demo"))
        page.locator("textarea").wait_for()
        inject_chrome(page)
        hold(page, 4000)

        with page.expect_file_chooser() as chooser:
            human_click(page, page.get_by_role("button", name="Attach document"))
        chooser.value.set_files(str(FIXTURE))
        page.locator(".upload-state", has_text="active").wait_for(timeout=60_000)
        hold(page, 800)
        smooth_scroll(page, ".upload-chip", 700)
        hold(page, 6000)

        type_and_send(
            page,
            "According to this document, who approves a claim of INR 45,000?",
            hold_ms=11000,
        )

        human_click(page, page.locator("button.new-chat"))
        page.locator(".empty h2").wait_for()
        hold(page, 3500)

        type_and_send(
            page,
            "An employee submits an expense claim for ₹15,000. Who needs to approve it?",
            hold_ms=10000,
        )

        click_format(page, "JSON", 6000)
        click_format(page, "XML", 5500)
        with page.expect_download(timeout=30_000) as dl:
            click_format(page, "Excel", 4500)
        download = dl.value
        dest = OUT_DIR / (download.suggested_filename or "prism_demo.xlsx")
        download.save_as(str(dest))
        click_format(page, "Email", 8500)

        type_and_send(
            page,
            "My toilet is occasionally leaking or running. What should I check?",
            hold_ms=11000,
        )
        type_and_send(page, "actually is that covered under warranty", hold_ms=10000)

        human_click(page, page.locator("button.brand-home"))
        page.get_by_role("heading", name="One query, any format.").wait_for()
        inject_chrome(page)
        hold(page, 12000)

        video_path = Path(page.video.path()) if page.video else None
        context.close()
        browser.close()

    if not video_path or not video_path.exists():
        recorded = list(OUT_DIR.glob("*.webm"))
        if not recorded:
            raise SystemExit("Playwright did not write a video")
        video_path = recorded[0]

    final_webm = OUT_DIR / "prism_demo_silent.webm"
    if video_path.resolve() != final_webm.resolve():
        if final_webm.exists():
            final_webm.unlink()
        video_path.replace(final_webm)

    final_mp4 = OUT_DIR / "prism_demo_silent.mp4"
    ffmpeg = str(FFMPEG) if FFMPEG.exists() else shutil.which("ffmpeg")
    if ffmpeg:
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-i",
                str(final_webm),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-crf",
                "20",
                "-an",
                str(final_mp4),
            ],
            check=True,
        )
        print(f"wrote {final_mp4} ({final_mp4.stat().st_size // 1024} KB)")
    else:
        print("ffmpeg not on PATH; leaving WebM")

    print(f"wrote {final_webm} ({final_webm.stat().st_size // 1024} KB)")
    return final_mp4 if final_mp4.exists() else final_webm


if __name__ == "__main__":
    t0 = time.time()
    path = run()
    print(f"done in {time.time() - t0:.1f}s -> {path}")
