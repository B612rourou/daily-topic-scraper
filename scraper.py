#!/usr/bin/env python3
import html
import os
import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

import requests

try:
    from duckduckgo_search import DDGS
except Exception as exc:
    raise SystemExit("缺少依赖 duckduckgo_search，请先安装：pip install duckduckgo_search") from exc

TZ = ZoneInfo("Asia/Shanghai")
NOW = datetime.now(TZ)
DATE_STR = NOW.strftime("%Y-%m-%d")
TIME_STR = NOW.strftime("%Y-%m-%d %H:%M:%S")
CUTOFF = NOW - timedelta(days=3)

OUT_DIR = "每日选题"
OUT_PATH = os.path.join(OUT_DIR, f"{DATE_STR}-daily-topics.md")

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

DDG_QUERIES = [
    "糖尿病 运动 控糖 亲身经历",
    "控糖 亲身经历 运动",
    "降糖 运动 实测",
    "糖尿病 运动 误区 真相",
    "糖化 下降 力量训练",
    "大龄 撸铁 控糖",
    "site:zhihu.com 糖尿病 运动 控糖",
    "site:bilibili.com 糖尿病 运动 控糖",
    "site:mp.weixin.qq.com 糖尿病 运动 控糖",
]

BILI_KEYWORDS = [
    "糖尿病 运动",
    "控糖 亲身经历",
    "降糖 运动",
    "力量训练 控糖",
    "大龄 撸铁 控糖",
]

ALLOWED_DOMAINS = {
    "zhihu.com", "m.zhihu.com",
    "bilibili.com", "b23.tv",
    "weibo.com", "weibo.cn",
    "mp.weixin.qq.com",
    "toutiao.com", "jinritoutiao.com",
    "douyin.com",
    "kuaishou.com",
    "xiaohongshu.com",
    "sina.com.cn",
    "thepaper.cn",
}

BLOCKED_DOMAINS = {
    "baike.baidu.com",
    "baike.com",
    "baike.so.com",
    "zh.wikipedia.org",
    "wikipedia.org",
    "wikiwand.com",
}

KEYWORD_WEIGHTS = {
    "亲测": 8, "实测": 8, "亲身经历": 8, "自述": 6,
    "误区": 6, "真相": 6, "反弹": 5, "反升": 5, "别再": 4,
    "血糖": 5, "糖化": 6, "HbA1c": 6, "胰岛素": 5, "停针": 6,
    "餐后": 5, "降糖": 5, "控糖": 4,
    "力量训练": 6, "撸铁": 6, "深蹲": 5, "动作": 4, "训练": 3,
}

MAX_ITEMS = 10
BILI_QUOTA = 6
STRICT_SOURCE = True
ALLOW_UNKNOWN_TIME = False


def norm_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    p = urlparse(url)
    if not p.scheme:
        return url.lower().rstrip("/")
    return f"{p.scheme}://{p.netloc}{p.path}".lower().rstrip("/")


def get_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def is_blocked_domain(domain: str) -> bool:
    if not domain:
        return True
    for bad in BLOCKED_DOMAINS:
        if domain == bad or domain.endswith("." + bad):
            return True
    return False


def is_allowed_domain(domain: str) -> bool:
    if not domain:
        return False
    for ok in ALLOWED_DOMAINS:
        if domain == ok or domain.endswith("." + ok):
            return True
    return False


def parse_relative_time(text: str):
    if not text:
        return None
    m = re.search(r"(\\d+)\\s*(分钟|分钟前)", text)
    if m:
        return NOW - timedelta(minutes=int(m.group(1)))
    m = re.search(r"(\\d+)\\s*(小时|小时前)", text)
    if m:
        return NOW - timedelta(hours=int(m.group(1)))
    m = re.search(r"(\\d+)\\s*天前", text)
    if m:
        return NOW - timedelta(days=int(m.group(1)))
    return None


def parse_date_text(text: str):
    if not text:
        return None
    m = re.search(r"(\\d{4})[./-](\\d{1,2})[./-](\\d{1,2})", text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return datetime(y, mo, d, tzinfo=TZ)
    m = re.search(r"(\\d{1,2})月(\\d{1,2})日", text)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        return datetime(NOW.year, mo, d, tzinfo=TZ)
    return None


def extract_datetime(item):
    date_str = (item.get("date") or "").strip()
    if date_str:
        try:
            if date_str.endswith("Z"):
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            else:
                dt = datetime.fromisoformat(date_str)
            return dt.astimezone(TZ)
        except Exception:
            pass
    text = f"{item.get('title','')} {item.get('body','')}"
    dt = parse_relative_time(text)
    if dt:
        return dt
    return parse_date_text(text)


def is_recent(dt):
    return dt and dt >= CUTOFF


def clean_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def search_ddg(query: str, max_results: int = 30):
    results = []
    try:
        ddgs = DDGS()
        try:
            results_iter = ddgs.text(query, timelimit="w", max_results=max_results)
        except TypeError:
            results_iter = ddgs.text(query, timelimit="w")
        for r in results_iter:
            if isinstance(r, dict):
                results.append(r)
            if len(results) >= max_results:
                break
    except Exception:
        return []
    return results


def calc_score(title: str, body: str, rank: int, domain: str) -> int:
    text = f"{title} {body}"
    score = max(0, 90 - rank)
    if "zhihu.com" in domain:
        score += 10
    if "bilibili.com" in domain or "b23.tv" in domain:
        score += 10
    for k, w in KEYWORD_WEIGHTS.items():
        if k in text:
            score += w
    if re.search(r"\\d", text):
        score += 4
    return max(10, min(150, score))


def gen_reason(title: str, body: str) -> str:
    text = f"{title} {body}"
    reasons = []
    if any(k in text for k in ["误区", "真相", "别再", "反弹", "反升"]):
        reasons.append("反常识/纠错型话题，容易引发讨论")
    if any(k in text for k in ["亲测", "实测", "亲身经历", "自述"]):
        reasons.append("真实案例增强可信度，适合爆款传播")
    if re.search(r"\\d", text):
        reasons.append("包含具体数字，具备量化对比记忆点")
    if any(k in text for k in ["动作", "训练", "力量", "深蹲", "运动"]):
        reasons.append("可操作性强，适合做步骤演示")
    if any(k in text for k in ["血糖", "糖化", "胰岛素", "餐后", "降糖", "控糖"]):
        reasons.append("直击糖友核心痛点，强搜索需求")
    if not reasons:
        reasons.append("聚焦控糖高热词，覆盖面广")
    return "；".join(reasons[:3])


def parse_play(value):
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    m = re.match(r"([\\d.]+)\\s*万", text)
    if m:
        return int(float(m.group(1)) * 10000)
    m = re.match(r"([\\d.]+)\\s*亿", text)
    if m:
        return int(float(m.group(1)) * 100000000)
    try:
        return int(float(text))
    except Exception:
        return 0


def fetch_bilibili():
    items = []
    url = "https://api.bilibili.com/x/web-interface/search/type"
    headers = {"User-Agent": USER_AGENT, "Referer": "https://search.bilibili.com"}
    for kw in BILI_KEYWORDS:
        params = {
            "search_type": "video",
            "keyword": kw,
            "page": 1,
            "order": "click",
        }
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            data = resp.json()
        except Exception:
            continue
        if data.get("code") != 0:
            continue
        for r in data.get("data", {}).get("result", []) or []:
            pub_ts = r.get("pubdate")
            if not pub_ts:
                continue
            pub_dt = datetime.fromtimestamp(int(pub_ts), tz=TZ)
            if not is_recent(pub_dt):
                continue
            title = clean_html(r.get("title") or "")
            if not title:
                continue
            url_item = r.get("arcurl") or ""
            play = parse_play(r.get("play"))
            items.append({
                "title": title,
                "url": url_item,
                "score": play,
                "reason": "B站热度排序结果，且发布时间在3天内",
                "source": "B站",
            })
        time.sleep(0.5)
    return items


def fetch_web():
    items = []
    for q in DDG_QUERIES:
        for r in search_ddg(q, max_results=30):
            url = (r.get("href") or r.get("url") or r.get("link") or "").strip()
            if not url:
                continue
            domain = get_domain(url)
            if is_blocked_domain(domain):
                continue
            if STRICT_SOURCE and not is_allowed_domain(domain):
                continue
            dt = extract_datetime(r)
            if not is_recent(dt):
                if not (ALLOW_UNKNOWN_TIME and dt is None):
                    continue
            title = clean_html(r.get("title") or r.get("heading") or "")
            body = clean_html(r.get("body") or r.get("snippet") or "")
            if not title:
                title = body[:40] if body else "未命名选题"
            score = calc_score(title, body, 0, domain)
            items.append({
                "title": title,
                "url": url,
                "score": score,
                "reason": gen_reason(title, body),
                "source": domain,
            })
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


def merge_items(bili_items, web_items):
    bili_items = sorted(bili_items, key=lambda x: x["score"], reverse=True)
    web_items = sorted(web_items, key=lambda x: x["score"], reverse=True)
    result = []
    for item in bili_items[:BILI_QUOTA]:
        result.append(item)
    if len(result) < MAX_ITEMS:
        need = MAX_ITEMS - len(result)
        result.extend(web_items[:need])
    result = dedupe(result)
    if len(result) < MAX_ITEMS:
        extras = [i for i in (bili_items + web_items) if i not in result]
        result.extend(extras[: MAX_ITEMS - len(result)])
    return result[:MAX_ITEMS]


def pad_items(items, target=10):
    while len(items) < target:
        items.append({
            "title": "（3天内未抓到合格内容）请手动补充",
            "url": "待补充",
            "score": 0,
            "reason": "未发现满足“3天内+非百科+热点来源”条件的内容",
            "source": "系统",
        })
    return items


def build_markdown(items):
    lines = []
    lines.append(f"# 📅 {DATE_STR} 糖尿病运动控糖·选题候选库")
    lines.append(f"> 生成时间：{TIME_STR} | 来源：全网热搜")
    for i, item in enumerate(items, 1):
        lines.append(f"## {i}. [热度/播放量: {item['score']}] 标题：{item['title']}")
        lines.append(f"- 🔗 链接：{item['url']}")
        lines.append(f"- 🧐 推荐理由：{item['reason']}")
        lines.append("- 📝 人工批注：(留空，方便我后续编辑)")
        lines.append("- ✅ 状态：[ ] 待定  [ ] 采纳  [ ] 废弃")
        lines.append("---")
    return "\n".join(lines)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    bili_items = fetch_bilibili()
    web_items = fetch_web()
    items = merge_items(bili_items, web_items)
    items = pad_items(items, MAX_ITEMS)
    md = build_markdown(items)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"已生成：{OUT_PATH}")


if __name__ == "__main__":
    main()
