import os


def find_cookie_db_paths():
    paths = []
    local = os.environ.get("LOCALAPPDATA", "")
    for base in (
        os.path.join(local, "Google", "Chrome", "User Data"),
        os.path.join(local, "Microsoft", "Edge", "User Data"),
    ):
        if not os.path.isdir(base):
            continue
        for name in ("Default", "Profile 1", "Profile 2", "Profile 3"):
            p = os.path.join(base, name, "Network", "Cookies")
            if os.path.exists(p):
                paths.append(p)
    return paths


def try_get_cookie():
    try:
        import browser_cookie3  # type: ignore
    except Exception:
        print("browser-cookie3 not installed.")
        print("Please run: python -m pip install -r requirements.txt")
        return ""

    jar = None
    for getter in (getattr(browser_cookie3, "chrome", None), getattr(browser_cookie3, "edge", None)):
        if getter is None:
            continue
        try:
            jar = getter(domain_name="douyin.com")
            if jar:
                break
        except Exception:
            jar = None
    if not jar:
        return ""
    pairs = [f"{c.name}={c.value}" for c in jar if getattr(c, "name", "") and getattr(c, "value", "")]
    return "; ".join(pairs)


def main():
    cookie = try_get_cookie()
    if not cookie:
        print("No cookie extracted. Make sure you are logged in to douyin.com.")
        print("Try closing the browser and run this as Administrator.")
        paths = find_cookie_db_paths()
        if paths:
            print("Found browser cookie DBs:")
            for p in paths:
                print(" -", p)
        else:
            print("No Chrome/Edge cookie DB found. Use Chrome or Edge to login.")
        return 1
    out_path = "douyin_cookie.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(cookie)
    print(f"Cookie saved: {out_path} (len={len(cookie)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
