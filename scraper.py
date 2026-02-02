#!/usr/bin/env python3
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

try:
    from duckduckgo_search import DDGS
except Exception as exc:
    raise SystemExit("缺少依赖 duckduckgo_search，请先安装：pip install duckduckgo_search") from exc

TZ = ZoneInfo("Asia/Shanghai")
now = datetime.now(TZ)
DATE_STR = now.strftime("%Y-%m-%d")
TIME_STR = now.strftime("%Y-%m-%d %H:%M:%S")

OUT_DIR = "每日选题"
OUT_PATH = os.path.join(OUT_DIR, f"{DATE_STR}-daily-topics.md")

QUERIES = [
    "糖尿病 运动 控糖 亲身经历",
    "控糖 亲身经历 运动",
    "降糖 运动 实测",
    "糖尿病 运动 误区 真相",
    "糖化 下降 力量训练",
    "大龄 撸铁 控糖",
    "site:zhihu.com 糖尿病 运动 控糖",
    "site:bilibili.com 糖尿病 运动 控糖",
]

KEYWORD_WEIGHTS = {
    "亲测": 8, "实测": 8, "亲身经历": 8, "自述": 6,
    "误区": 6, "真相": 6, "反弹": 5, "反升": 5, "别再": 4,
    "血糖": 5, "糖化": 6, "HbA1c": 6, "胰岛素": 5, "停针": 6,
    "餐后": 5, "降糖": 5, "控糖": 4,
    "力量训练": 6, "撸铁": 6, "深蹲": 5, "动作": 4, "训练": 3,
}


def norm_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    p = urlparse(url)
    if not p.scheme:
        return url.lower().rstrip("/")
    return f"{p.scheme}://{p.netloc}{p.path}".lower().rstrip("/")


def search_ddg(query: str, max_results: int = 30):
    results = []
    try:
        ddgs = DDGS()
        try:
            results_iter = ddgs.text(query, timelimit="d", max_results=max_results)
        except TypeError:
            results_iter = ddgs.text(query, timelimit="d")
        for r in results_iter:
            if isinstance(r, dict):
                results.append(r)
            if len(results) >= max_results:
                break
    except Exception:
        return []
    return results


def calc_score(item: dict, rank: int) -> int:
    text = f"{item['title']} {item['body']}"
    score = max(0, 100 - rank)
    url = item["url"]
    if "zhihu.com" in url:
        score += 10
    if "bilibili.com" in url:
        score += 10
    for k, w in KEYWORD_WEIGHTS.items():
        if k in text:
            score += w
    if re.search(r"\d", text):
        score += 4
    return max(10, min(150, score))


def gen_reason(item: dict) -> str:
    text = f"{item['title']} {item['body']}"
    reasons = []
    if any(k in text for k in ["误区", "真相", "别再", "反弹", "反升"]):
        reasons.append("反常识/纠错型话题，容易引发讨论")
    if any(k in text for k in ["亲测", "实测", "亲身经历", "自述"]):
        reasons.append("真实案例增强可信度，适合爆款传播")
    if re.search(r"\d", text):
        reasons.append("包含具体数字，具备量化对比记忆点")
    if any(k in text for k in ["动作", "训练", "力量", "深蹲", "运动"]):
        reasons.append("可操作性强，适合做步骤演示")
    if any(k in text for k in ["血糖", "糖化", "胰岛素", "餐后", "降糖", "控糖"]):
        reasons.append("直击糖友核心痛点，强搜索需求")
    if not reasons:
        reasons.append("聚焦控糖高热词，覆盖面广")
    return "；".join(reasons[:3])


def collect_items():
    raw = []
    for q in QUERIES:
        for r in search_ddg(q, max_results=30):
            url = (r.get("href") or r.get("url") or r.get("link") or "").strip()
            if not url:
                continue
            title = (r.get("title") or r.get("heading") or "").strip()
            body = (r.get("body") or r.get("snippet") or "").strip()
            if not title:
                title = body[:40] if body else "未命名选题"
            raw.append({"title": title, "body": body, "url": url, "query": q})

    seen = set()
    items = []
    for item in raw:
        key = norm_url(item["url"])
        if not key or key in seen:
            continue
        seen.add(key)
        items.append(item)

    scored = []
    for idx, item in enumerate(items):
        score = calc_score(item, idx)
        scored.append({
            "title": item["title"],
            "url": item["url"],
            "score": score,
            "reason": gen_reason(item),
        })
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:10]


def pad_items(items, target=10):
    while len(items) < target:
        items.append({
            "title": "（今日未抓到结果）请手动补充",
            "url": "待补充",
            "score": 0,
            "reason": "暂无有效抓取结果，建议手动补充",
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
    items = collect_items()
    items = pad_items(items, 10)
    md = build_markdown(items)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"已生成：{OUT_PATH}")


if __name__ == "__main__":
    main()
