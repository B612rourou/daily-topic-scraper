import os
from playwright.sync_api import sync_playwright

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    profile_dir = os.path.join(base_dir, ".playwright_profile")
    os.makedirs(profile_dir, exist_ok=True)

    with sync_playwright() as p:
        context = None
        last_err = None
        for channel in ("chrome", "msedge"):
            try:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=profile_dir,
                    channel=channel,
                    headless=False,
                    args=["--disable-blink-features=AutomationControlled"],
                    user_agent=USER_AGENT,
                    viewport={"width": 1280, "height": 720},
                    locale="zh-CN",
                )
                print(f"Using browser channel: {channel}")
                break
            except Exception as exc:
                last_err = exc
                context = None
        if context is None:
            print("Failed to launch Chrome/Edge. Please install Chrome or Edge.")
            if last_err:
                print("Error:", last_err)
            return 1

        page = context.new_page()
        page.goto("https://www.douyin.com", wait_until="domcontentloaded", timeout=60000)
        print("\nPlease login in the opened browser, then come back here and press Enter.")
        input("Press Enter after login...")

        cookies = context.cookies("https://www.douyin.com")
        cookie_str = "; ".join(
            [f"{c.get('name')}={c.get('value')}" for c in cookies if c.get("name") and c.get("value")]
        )
        if not cookie_str:
            print("No cookie captured. Maybe not logged in or blocked.")
            context.close()
            return 1

        out_path = "douyin_cookie.txt"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(cookie_str)
        print(f"Cookie saved: {out_path} (len={len(cookie_str)})")
        context.close()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
