"""Exercise the UI with an isolated, explicitly non-AI test provider."""

import argparse
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import uvicorn
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import Settings
from app.main import create_app
from tests.fakes import PublicTestProvider, TestProvider


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--public", action="store_true", help="Test public-mode consent with an offline fixture"
    )
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as data, socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        settings = Settings(_env_file=None, data_dir=Path(data), api_key="browser-test")
        server = uvicorn.Server(
            uvicorn.Config(
                create_app(settings, PublicTestProvider() if args.public else TestProvider()),
                host="127.0.0.1",
                port=port,
                log_level="error",
            )
        )
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        output = ROOT / "test-results"
        output.mkdir(exist_ok=True)
        errors = []
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                page = browser.new_page(viewport={"width": 1440, "height": 1080}, device_scale_factor=1)
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{port}")
                expect(page.locator("#generate")).to_be_disabled()
                page.get_by_role("button", name="连接设置").click()
                page.locator("#api-key").fill("browser-test")
                page.get_by_role("button", name="连接工作空间").click()
                expect(page.locator("#engine-label")).to_contain_text("已配置")
                page.screenshot(path=str(output / "studio-desktop.png"), full_page=True)
                page.locator("#model-input").set_input_files(
                    {"name": "broken.png", "mimeType": "image/png", "buffer": b"bad"}
                )
                expect(page.locator("#toast")).to_have_class("toast error")
                page.get_by_role("button", name="试用示例图片").click()
                if args.public:
                    expect(page.locator("#preserve")).to_be_disabled()
                    expect(page.locator("#generate")).to_be_disabled()
                    page.locator("#public-consent").check()
                expect(page.locator("#generate")).to_be_enabled()
                expect(page.locator("#photo-type")).to_have_value("model")
                page.locator('[name="category"][value="outerwear"]').check()
                page.locator("#generate").click()
                expect(page.locator("#result-preview")).to_be_visible(timeout=15000)
                expect(page.locator("#working")).to_be_hidden(timeout=15000)
                page.get_by_role("button", name="前后对比", exact=True).click()
                expect(page.locator("#before-layer")).to_be_visible()
                page.locator("#compare-range").fill("30")
                assert "70%" in page.locator("#before-layer").get_attribute("style")
                with page.expect_download() as download:
                    page.get_by_role("button", name="下载 PNG").click()
                assert download.value.suggested_filename.endswith(".png")
                page.screenshot(path=str(output / "compare-test-fixture.png"), full_page=True)
                page.get_by_role("button", name="最近记录").click()
                expect(page.locator(".session-card")).to_have_count(1)
                page.get_by_role("button", name="查看记录").click()
                expect(page.locator("#result-preview")).to_be_visible(timeout=15000)
                expect(page.locator("#working")).to_be_hidden(timeout=15000)
                page.get_by_role("button", name="新建试衣").click()
                if args.public:
                    expect(page.locator("#public-consent")).not_to_be_checked()
                expect(page.locator("#model-thumb")).to_be_hidden()
                expect(page.locator("#generate")).to_be_disabled()
                page.get_by_role("button", name="最近记录").click()
                page.get_by_role("button", name="删除", exact=True).click()
                expect(page.locator(".session-card")).to_have_count(0)
                page.get_by_role("button", name="试衣工作台").click()
                page.set_viewport_size({"width": 390, "height": 844})
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                page.screenshot(path=str(output / "studio-mobile.png"), full_page=True)
                assert not errors, errors
                browser.close()
        finally:
            server.should_exit = True
            thread.join(timeout=10)
    print(
        "Browser checks passed: auth, upload validation, samples, generation, compare, download, history, delete, mobile."
    )


if __name__ == "__main__":
    main()
