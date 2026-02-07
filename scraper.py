#!/usr/bin/env python3
import base64
import html
import json
import os
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import quote, urlparse, parse_qs

import requests

TZ = ZoneInfo("Asia/Shanghai")
NOW = datetime.now(TZ)
DATE_STR = NOW.strftime("%Y-%m-%d")
TIME_STR = NOW.strftime("%Y-%m-%d %H:%M:%S")
STRICT_DAYS = int(os.environ.get("STRICT_DAYS", 3))
MAX_DAYS = int(os.environ.get("MAX_DAYS", 7))
CUTOFF = NOW - timedelta(days=STRICT_DAYS)
MAX_CUTOFF = NOW - timedelta(days=MAX_DAYS)

OUT_DIR = "每日选题"
OUT_PATH = os.path.join(OUT_DIR, f"{DATE_STR}-daily-topics.md")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

DOUYIN_HOT_API = "https://aweme-hl.snssdk.com/aweme/v1/hot/search/list/?detail_list=1"

KEYWORD_WEIGHTS = {
    "亲测": 8, "实测": 8, "亲身经历": 8, "自述": 6,
    "误区": 6, "真相": 6, "反弹": 5, "反升": 5, "别再": 4,
    "血糖": 5, "糖化": 6, "HbA1c": 6, "胰岛素": 5, "停针": 6,
    "餐后": 5, "降糖": 5, "控糖": 4,
    "力量训练": 6, "撸铁": 6, "深蹲": 5, "动作": 4, "训练": 3,
}

CORE_KEYWORDS = [
    "糖尿病", "控糖", "降糖", "血糖", "糖化", "胰岛素", "餐后",
]

FITNESS_KEYWORDS = [
    "运动", "健身", "力量", "增肌", "减脂", "有氧", "无氧", "深蹲",
    "跑步", "走路", "训练", "燃脂",
]

EXTENDED_KEYWORDS = [
    "减肥", "体重", "代谢", "健康", "养生", "饮食", "低碳",
]

SEARCH_KEYWORDS = [
    "糖尿病 运动",
    "控糖 亲身经历",
    "降糖 运动",
    "控糖 力量训练",
    "糖化 血红蛋白",
]

MAX_ITEMS = 10
MIN_HOT_VALUE = 1_000_000
MIN_PLAY_COUNT = int(os.environ.get("MIN_PLAY_COUNT", 50000))
MIN_ENGAGEMENT_SCORE = int(os.environ.get("MIN_ENGAGEMENT_SCORE", 3000))
ALLOW_HOT_FALLBACK = False
HEADLESS = os.environ.get("HEADLESS", "1") != "0"
DEBUG = os.environ.get("DEBUG", "0") == "1"
HAR_FIRST = os.environ.get("HAR_FIRST", "1") != "0"
SKIP_PLAYWRIGHT = os.environ.get("SKIP_PLAYWRIGHT", "0") == "1"

PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.sync_api import sync_playwright  # type: ignore
    PLAYWRIGHT_AVAILABLE = True
except Exception:
    PLAYWRIGHT_AVAILABLE = False

STEALTH_AVAILABLE = False
try:
    from playwright_stealth import stealth_sync  # type: ignore
    STEALTH_AVAILABLE = True
except Exception:
    STEALTH_AVAILABLE = False

LAST_PLAYWRIGHT_ERROR = ""


def norm_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    p = urlparse(url)
    if not p.scheme:
        return url.lower().rstrip("/")
    return f"{p.scheme}://{p.netloc}{p.path}".lower().rstrip("/")


def clean_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def is_recent(dt, cutoff):
    return dt and dt >= cutoff


def safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def is_vertical_text(text: str) -> bool:
    if not text:
        return False
    core = any(k in text for k in CORE_KEYWORDS)
    fitness = any(k in text for k in FITNESS_KEYWORDS)
    extended = any(k in text for k in EXTENDED_KEYWORDS)
    return core or (fitness and extended)


def extract_cookie_from_har(path: str) -> str:
    if not path or not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            data = json.load(f)
    except Exception:
        return ""

    entries = data.get("log", {}).get("entries", [])
    # 优先找 request headers 里的 cookie
    for e in entries:
        headers = {h["name"].lower(): h["value"] for h in e.get("request", {}).get("headers", [])}
        cookie = headers.get("cookie", "")
        if cookie:
            return cookie
    # 其次找 request cookies 列表
    for e in entries:
        cookies = e.get("request", {}).get("cookies", [])
        if cookies:
            return "; ".join([f"{c.get('name')}={c.get('value')}" for c in cookies if c.get("name")])
    return ""


def load_cookie():
    cookie = os.environ.get("DOUYIN_COOKIE", "").strip()
    if cookie:
        return cookie
    cookie_file = "douyin_cookie.txt"
    if os.path.exists(cookie_file):
        try:
            with open(cookie_file, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            pass
    legacy_file = "抖音Cookie.txt"
    if os.path.exists(legacy_file):
        try:
            with open(legacy_file, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            pass
    # 尝试从 HAR 自动提取
    har_candidates = [
        os.path.join("日志", "www.douyin.com.har"),
        os.path.join(os.path.dirname(__file__), "..", "日志", "www.douyin.com.har"),
        os.path.join(os.path.dirname(__file__), "日志", "www.douyin.com.har"),
    ]
    for har_path in har_candidates:
        har_path = os.path.normpath(har_path)
        cookie = extract_cookie_from_har(har_path)
        if cookie:
            try:
                with open(cookie_file, "w", encoding="utf-8") as f:
                    f.write(cookie)
            except Exception:
                pass
            return cookie
    # 尝试从本机浏览器直接读取（Chrome/Edge）
    try:
        import browser_cookie3  # type: ignore
        jar = None
        try:
            jar = browser_cookie3.chrome(domain_name="douyin.com")
        except Exception:
            jar = None
        if jar is None:
            try:
                jar = browser_cookie3.edge(domain_name="douyin.com")
            except Exception:
                jar = None
        if jar:
            cookie = "; ".join([f"{c.name}={c.value}" for c in jar if c.name and c.value])
            if cookie:
                try:
                    with open(cookie_file, "w", encoding="utf-8") as f:
                        f.write(cookie)
                except Exception:
                    pass
                return cookie
    except Exception:
        pass
    return cookie


def parse_cookie_to_list(cookie_str: str):
    cookies = []
    if not cookie_str:
        return cookies
    for part in cookie_str.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        cookies.append({
            "name": name.strip(),
            "value": value.strip(),
            "domain": ".douyin.com",
            "path": "/",
        })
    return cookies


def find_browser_profile():
    env_dir = os.environ.get("DOUYIN_PROFILE_DIR")
    env_name = os.environ.get("DOUYIN_PROFILE_NAME")
    if env_dir:
        profile = env_name or "Default"
        if os.path.isdir(os.path.join(env_dir, profile)):
            return env_dir, profile, "chrome"
    local = os.environ.get("LOCALAPPDATA", "")
    chrome_base = os.path.join(local, "Google", "Chrome", "User Data")
    if os.path.isdir(os.path.join(chrome_base, "Default")):
        return chrome_base, "Default", "chrome"
    edge_base = os.path.join(local, "Microsoft", "Edge", "User Data")
    if os.path.isdir(os.path.join(edge_base, "Default")):
        return edge_base, "Default", "msedge"
    return None


def iter_chunk_bodies(raw: bytes):
    if not raw:
        return []
    j0 = raw.find(b"\r\n")
    if j0 == -1:
        return [raw]
    size_hex = raw[:j0].decode("ascii", errors="ignore").strip()
    if not re.fullmatch(r"[0-9a-fA-F]+", size_hex or ""):
        return [raw]
    bodies = []
    i = 0
    n = len(raw)
    while i < n:
        j = raw.find(b"\r\n", i)
        if j == -1:
            break
        size_hex = raw[i:j].decode("ascii", errors="ignore").strip()
        try:
            size = int(size_hex, 16)
        except Exception:
            break
        if size == 0:
            break
        start = j + 2
        end = start + size
        bodies.append(raw[start:end])
        i = end + 2
    return bodies


def parse_search_jsons(raw: bytes):
    if not raw:
        return []
    # 合并分块数据
    body = b"".join(iter_chunk_bodies(raw))
    try:
        text = body.decode("utf-8", errors="ignore")
    except Exception:
        return []
    decoder = json.JSONDecoder()
    s = text.strip()
    objs = []
    while s:
        try:
            obj, idx = decoder.raw_decode(s)
        except Exception:
            break
        objs.append(obj)
        s = s[idx:].lstrip()
    if objs:
        return objs
    # 兜底：尝试截取首尾 JSON
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return [json.loads(text[start:end + 1])]
        except Exception:
            return []
    return []


def extract_aweme_items(data, keyword: str):
    items = []
    if not data:
        return items
    data_list = data.get("data") or []
    for entry in data_list:
        if entry.get("type") != 1:
            continue
        aweme = entry.get("aweme_info") or {}
        aweme_id = aweme.get("aweme_id") or aweme.get("aweme_id_str")
        desc = clean_html(aweme.get("desc") or "")
        if not aweme_id or not desc:
            continue
        if not any(k in desc for k in CORE_KEYWORDS + FITNESS_KEYWORDS):
            continue
        vertical = is_vertical_text(desc)
        create_time = safe_int(aweme.get("create_time"))
        dt = datetime.fromtimestamp(create_time, tz=TZ) if create_time else None
        if not is_recent(dt, MAX_CUTOFF):
            continue
        overdue = not is_recent(dt, CUTOFF)
        stats = aweme.get("statistics") or {}
        play = safe_int(stats.get("play_count") or stats.get("view_count"))
        digg = safe_int(stats.get("digg_count"))
        comment = safe_int(stats.get("comment_count"))
        share = safe_int(stats.get("share_count"))
        collect = safe_int(stats.get("collect_count"))
        engagement = digg + comment * 5 + share * 8 + collect * 3
        if play > 0 and play < MIN_PLAY_COUNT:
            continue
        if play == 0 and engagement < MIN_ENGAGEMENT_SCORE:
            continue
        hot_value = play if play > 0 else engagement
        score = (play if play > 0 else 0) + engagement * 10
        tag = "垂直" if vertical else "相关"
        if play > 0:
            metric = f"播放{play}"
        else:
            metric = f"互动热度{engagement}（赞{digg}/评{comment}/藏{collect}/转{share}）"
        if overdue:
            time_tag = f"近{MAX_DAYS}天内（⚠超出{STRICT_DAYS}天）"
        else:
            time_tag = f"近{STRICT_DAYS}天"
        reason = (
            f"{time_tag}抖音关键词「{keyword}」搜索结果（{tag}），{metric}；"
            f"适合你用“54岁撸铁控糖大姐”的实测视角拆解"
        )
        items.append({
            "title": desc,
            "url": f"https://www.douyin.com/video/{aweme_id}",
            "score": score,
            "display": hot_value,
            "reason": reason,
            "datetime": dt,
            "priority": 1 if not overdue else 0,
        })
    return items


def fetch_douyin_by_playwright():
    global LAST_PLAYWRIGHT_ERROR
    LAST_PLAYWRIGHT_ERROR = ""
    if not PLAYWRIGHT_AVAILABLE:
        LAST_PLAYWRIGHT_ERROR = "Playwright not installed."
        return []
    cookie_str = load_cookie()
    cookies = parse_cookie_to_list(cookie_str)
    all_items = []
    raw_total = [0]
    try:
        with sync_playwright() as p:
            context = None
            browser = None
            profile = None if cookie_str else find_browser_profile()
            if profile:
                base_dir, profile_name, channel = profile
                if DEBUG:
                    print(f"使用浏览器配置: {base_dir} / {profile_name} ({channel})")
                try:
                    context = p.chromium.launch_persistent_context(
                        user_data_dir=base_dir,
                        channel=channel,
                        headless=HEADLESS,
                        args=[
                            "--disable-blink-features=AutomationControlled",
                            f"--profile-directory={profile_name}",
                        ],
                        user_agent=USER_AGENT,
                        viewport={"width": 1280, "height": 720},
                        locale="zh-CN",
                    )
                except Exception:
                    context = None
            if context is None:
                launch_errors = []
                for channel in ("chrome", "msedge"):
                    try:
                        browser = p.chromium.launch(
                            headless=HEADLESS,
                            channel=channel,
                            args=["--disable-blink-features=AutomationControlled"],
                        )
                        break
                    except Exception as e:
                        launch_errors.append(str(e))
                if browser is None:
                    try:
                        browser = p.chromium.launch(
                            headless=HEADLESS,
                            args=["--disable-blink-features=AutomationControlled"],
                        )
                    except Exception as e:
                        LAST_PLAYWRIGHT_ERROR = f"Playwright launch failed: {e}"
                        return []
                context = browser.new_context(
                    user_agent=USER_AGENT,
                    viewport={"width": 1280, "height": 720},
                    locale="zh-CN",
                )
            context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            if cookies:
                try:
                    context.add_cookies(cookies)
                except Exception:
                    pass
            # 先访问首页，让站点种必要的 Cookie
            home = context.new_page()
            if STEALTH_AVAILABLE:
                try:
                    stealth_sync(home)
                except Exception:
                    pass
            try:
                home.goto("https://www.douyin.com", wait_until="domcontentloaded", timeout=60000)
                home.wait_for_timeout(3000)
            except Exception:
                pass
            home.close()

            for kw in SEARCH_KEYWORDS:
                items = []

                def handle_response(resp):
                    url = resp.url
                    if "aweme/v1/web/general/search" not in url:
                        return
                    try:
                        raw = resp.body()
                    except Exception:
                        return
                    data_list = parse_search_jsons(raw)
                    if not data_list:
                        return
                    for data in data_list:
                        for entry in data.get("data") or []:
                            if entry.get("type") == 1 and entry.get("aweme_info"):
                                raw_total[0] += 1
                        items.extend(extract_aweme_items(data, kw))

                page = context.new_page()
                if STEALTH_AVAILABLE:
                    try:
                        stealth_sync(page)
                    except Exception:
                        pass
                page.on("response", handle_response)
                page.goto(
                    f"https://www.douyin.com/search/{quote(kw)}",
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
                page.wait_for_timeout(10000)
                page.close()
                if items:
                    print(f"关键词「{kw}」命中 {len(items)} 条")
                if items:
                    all_items.extend(items)
            context.close()
            browser.close()
    except Exception as e:
        LAST_PLAYWRIGHT_ERROR = f"Playwright error: {e}"
        return []
    print(f"Playwright raw {raw_total[0]} items, filtered {len(all_items)}")
    return all_items


def fetch_from_har():
    # 解析用户导出的 HAR 文件（不依赖实时请求）
    har_candidates = [
        os.path.join("日志", "www.douyin.com.har"),
        os.path.join(os.path.dirname(__file__), "..", "日志", "www.douyin.com.har"),
        os.path.join(os.path.dirname(__file__), "日志", "www.douyin.com.har"),
    ]
    har_path = None
    for p in har_candidates:
        p = os.path.normpath(p)
        if os.path.exists(p):
            har_path = p
            break
    if not har_path:
        return []
    try:
        with open(har_path, "r", encoding="utf-8", errors="ignore") as f:
            data = json.load(f)
    except Exception:
        return []

    items = []
    total_aweme = 0
    latest_dt = None
    entries = data.get("log", {}).get("entries", [])
    for e in entries:
        url = e.get("request", {}).get("url", "")
        if "aweme/v1/web/general/search" not in url:
            continue
        qs = parse_qs(urlparse(url).query)
        kw = qs.get("keyword", [""])[0]
        if not kw:
            kw = "抖音搜索"
        content = e.get("response", {}).get("content", {})
        raw = b""
        if content.get("encoding") == "base64":
            try:
                raw = base64.b64decode(content.get("text", "") or "")
            except Exception:
                raw = b""
        else:
            raw = (content.get("text", "") or "").encode("utf-8", errors="ignore")
        if not raw:
            continue
        for obj in parse_search_jsons(raw):
            data_list = obj.get("data") or []
            for entry in data_list:
                if entry.get("type") != 1:
                    continue
                aweme = entry.get("aweme_info") or {}
                create_time = safe_int(aweme.get("create_time"))
                dt = datetime.fromtimestamp(create_time, tz=TZ) if create_time else None
                if dt and (latest_dt is None or dt > latest_dt):
                    latest_dt = dt
                total_aweme += 1
            items.extend(extract_aweme_items(obj, kw))
    if not items and total_aweme > 0:
        hint = f"HAR 中有 {total_aweme} 条视频，但均超出近{MAX_DAYS}天或热度不足。"
        if latest_dt:
            hint += f" 最新时间：{latest_dt.strftime('%Y-%m-%d %H:%M:%S')}。"
        print(hint)
    return items


def calc_hot_score(title: str, hot_value: int, dt: datetime):
    text = title
    score = hot_value
    if dt:
        age_hours = (NOW - dt).total_seconds() / 3600
        if age_hours <= 24:
            score += 20000
        elif age_hours <= 48:
            score += 10000
        elif age_hours <= 72:
            score += 5000
    for k, w in KEYWORD_WEIGHTS.items():
        if k in text:
            score += w * 100
    return score


def safe_json_load(text: str):
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return None
    clean = text[start:end + 1]
    try:
        return json.loads(clean)
    except Exception:
        return None


def fetch_douyin_hot():
    items = []
    headers = {"User-Agent": USER_AGENT, "Referer": "https://www.douyin.com"}
    try:
        resp = requests.get(DOUYIN_HOT_API, headers=headers, timeout=10)
        if resp.status_code != 200:
            return []
        data = safe_json_load(resp.text)
        if not data:
            return []
    except Exception:
        return []

    word_list = []
    data_block = data.get("data")
    if isinstance(data_block, dict) and "word_list" in data_block:
        word_list = data_block.get("word_list") or []
    elif "word_list" in data:
        word_list = data.get("word_list") or []

    def keyword_hits(word: str, keywords):
        return [k for k in keywords if k in word]

    tier1_items = []  # 垂直：命中核心控糖/糖尿病
    tier2_items = []  # 相关：命中运动/饮食/减脂等
    tier3_items = []  # 借势：其他热搜

    for w in word_list:
        word = w.get("word") or ""
        if not word:
            continue
        hot_value = safe_int(w.get("hot_value"))
        if hot_value < MIN_HOT_VALUE:
            continue
        event_time = w.get("event_time")
        dt = None
        if event_time:
            dt = datetime.fromtimestamp(safe_int(event_time), tz=TZ)
        if not is_recent(dt, CUTOFF):
            continue
        url = f"https://www.douyin.com/search/{quote(word)}"
        score = calc_hot_score(word, hot_value, dt)
        core_hits = keyword_hits(word, CORE_KEYWORDS)
        fitness_hits = keyword_hits(word, FITNESS_KEYWORDS)
        extended_hits = keyword_hits(word, EXTENDED_KEYWORDS)
        hits = core_hits + fitness_hits + extended_hits

        if core_hits:
            hit_text = "、".join(hits) if hits else "无"
            reason = f"抖音热搜榜话题（热度值），3天内更新；命中关键词：{hit_text}"
            title = f"【垂直】{word}"
            bucket = tier1_items
        elif fitness_hits or extended_hits:
            hit_text = "、".join(hits) if hits else "无"
            reason = f"抖音热搜榜话题（热度值），3天内更新；命中相关关键词：{hit_text}"
            title = f"【相关】{word}"
            bucket = tier2_items
        else:
            reason = "抖音全站热搜（非垂直关键词），可用于借势改写为控糖角度"
            title = f"【借势】{word}"
            bucket = tier3_items

        bucket.append({
            "title": title,
            "url": url,
            "score": score,
            "display": hot_value,
            "reason": reason,
            "datetime": dt,
        })

    if ALLOW_HOT_FALLBACK:
        items = tier1_items + tier2_items + tier3_items
    else:
        items = tier1_items
    return items


def dedupe(items):
    seen = set()
    out = []
    for item in items:
        key = norm_url(item["url"]) or item["title"]
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def select_top(items):
    def sort_key(x):
        dt = x.get("datetime")
        ts = dt.timestamp() if dt else 0
        return (x.get("priority", 0), x.get("score", 0), ts)

    items = dedupe(items)
    items.sort(key=sort_key, reverse=True)
    return items[:MAX_ITEMS]


def pad_items(items, target=10):
    while len(items) < target:
        items.append({
            "title": "（3天内未抓到合格内容）请手动补充",
            "url": "待补充",
            "score": 0,
            "display": 0,
            "reason": f"未抓到抖音“控糖/糖尿病”相关热度内容（近{STRICT_DAYS}天）；可能是反爬或Cookie/Har无效",
        })
    return items


def build_markdown(items):
    lines = []
    lines.append(f"# 📅 {DATE_STR} 糖尿病运动控糖·选题候选库")
    lines.append(f"> 生成时间：{TIME_STR} | 来源：抖音搜索（近{STRICT_DAYS}天优先）")
    for i, item in enumerate(items, 1):
        lines.append(f"## {i}. [热度/播放量: {item.get('display', item['score'])}] 标题：{item['title']}")
        lines.append(f"- 🔗 链接：{item['url']}")
        lines.append(f"- 🧐 推荐理由：{item['reason']}")
        lines.append("- 📝 人工批注：(留空，方便我后续编辑)")
        lines.append("- ✅ 状态：[ ] 待定  [ ] 采纳  [ ] 废弃")
        lines.append("---")
    return "\n".join(lines)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    items = []
    if HAR_FIRST:
        items = fetch_from_har()
        if items:
            print(f"HAR 命中 {len(items)} 条")
    if not items and not SKIP_PLAYWRIGHT:
        items = fetch_douyin_by_playwright()
        if not items and LAST_PLAYWRIGHT_ERROR:
            print(LAST_PLAYWRIGHT_ERROR)
    if not items:
        items = fetch_from_har()
        if items:
            print(f"HAR 命中 {len(items)} 条")
    if not items and ALLOW_HOT_FALLBACK:
        items = fetch_douyin_hot()
    items = select_top(items)
    items = pad_items(items, MAX_ITEMS)
    md = build_markdown(items)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"已生成：{OUT_PATH}")


if __name__ == "__main__":
    import sys
    if "--extract-cookie" in sys.argv:
        cookie = load_cookie()
        if cookie:
            print(f"已提取Cookie，长度：{len(cookie)}。已写入 douyin_cookie.txt")
        else:
            print("未提取到Cookie，请确认已登录抖音并以管理员身份运行。")
        raise SystemExit(0)
    main()
