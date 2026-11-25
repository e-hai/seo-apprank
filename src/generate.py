# -*- coding: utf-8 -*-
"""
generate.py — 应用榜单 SEO 静态页生成器
消费 e-hai/Appstore_Top_30 的静态 JSON API，生成合规的程序化 SEO 页面。

合规护栏（来自研究结论）：
1. 每页必须有随数据变化的原创洞察（insight）——不是变量替换
2. 方法论 + 数据来源归因 + Last updated
3. 7d/30d 排名变化 + 趋势图
4. 交互筛选器（抵抗 AI 摘要吞掉）
5. schema 与可见内容一致；FAQ schema 已停用不做
6. 单站、小批量、可清理

运行： python3 src/generate.py --out site --sample
      python3 src/generate.py --out site   # 全量
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import urllib.request
import concurrent.futures
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import config as C
import incremental as INC
import locales as L

# ---------------------------------------------------------------------------
# 数据层
# ---------------------------------------------------------------------------
def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": C.UA})
    with urllib.request.urlopen(req, timeout=C.REQUEST_TIMEOUT) as r:
        return json.load(r)

def get_latest_dates(n: int = 1) -> list[str]:
    d = fetch_json(f"{C.API_BASE}/dates.json")
    return [x["date"] for x in d["dates"][-n:]]

def get_ranking(store: str, market: str, chart: str, date: str, genre: str | None = None) -> dict:
    parts = [store, market, chart]
    if genre:
        parts.append(genre)
    parts.append(date)
    name = "_".join(parts) + ".json"
    return fetch_json(f"{C.API_BASE}/rankings/{name}")

def get_trend(store: str, market: str, chart: str) -> dict:
    return fetch_json(f"{C.API_BASE}/trend/{store}_{market}_{chart}.json")

# ---------------------------------------------------------------------------
# 洞察计算 —— 这是"原创内容"的核心，全部基于真实数据计算
# ---------------------------------------------------------------------------
def make_description(insight: str, limit: int = 158) -> str:
    """把洞察段压成一条完整、不半截断句的 meta description。
    优先在句子边界截断，句内超长时退到词边界并加省略号，绝不切出 "No apps " 这种残句。"""
    text = re.sub(r"\s+", " ", insight).strip()
    if len(text) <= limit:
        return text
    # 在 limit 内找最后一个句子结束点（句号/分号/问号/感叹号 + 空格）
    window = text[: limit + 1]
    ends = [m.end() for m in re.finditer(r"[.!?;]\s", window)]
    if ends and ends[-1] >= limit * 0.55:
        return text[: ends[-1] - 1].rstrip(" .!?;:") + "."
    # 否则退到词边界
    cut = text[:limit]
    sp = cut.rfind(" ")
    if sp >= limit * 0.5:
        return cut[:sp].rstrip() + "…"
    return cut.rstrip(" ,;:") + "…"

def compute_insights(rows: list[dict], trend: dict, date: str, market: str, chart: str, lang: str) -> dict:
    """从真实数据算出可写进正文的洞察点。避免模板套话。"""
    new_apps = [r for r in rows if r.get("status") == "new"]
    risers = sorted([r for r in rows if (r.get("rank_change") or 0) > 0],
                    key=lambda r: r["rank_change"], reverse=True)[:3]
    fallers = sorted([r for r in rows if (r.get("rank_change") or 0) < 0],
                     key=lambda r: r["rank_change"])[:3]
    stable = [r for r in rows if r.get("status") == "stable"]
    top = rows[0] if rows else {}
    devs: dict[str, int] = {}
    genres: dict[str, int] = {}
    for r in rows:
        devs[r.get("developer", "")] = devs.get(r.get("developer", ""), 0) + 1
        genres[r.get("genre_name", "")] = genres.get(r.get("genre_name", ""), 0) + 1
    top_dev, top_dev_n = max(devs.items(), key=lambda kv: kv[1]) if devs else ("", 0)
    top_genre, top_genre_n = max(genres.items(), key=lambda kv: kv[1]) if genres else ("", 0)

    # 趋势：新进榜的 app 在趋势里的最长在榜天数
    longest = 0
    trend_map = trend.get("trends", {})
    for r in rows[:10]:
        series = trend_map.get(r.get("app_id"), [])
        if series:
            longest = max(longest, len(series))

    mkt = C.market_name(market, lang)
    ch = C.CHARTS[chart][lang]
    n = len(rows)
    I = L.get(lang)["insight"]
    # 当 new 占比过高（如数据源首次抓取该榜），"N new entries" 会失真且无意义，
    # 改用稳健描述：只陈述榜单构成事实，不夸大"异动"。
    new_ratio = len(new_apps) / n if n else 0
    new_phrase = (
        I["new_low"].format(n=len(new_apps)) if new_ratio <= 0.5 else I["new_high"]
    )
    mover_phrase = (
        I["mover"].format(name=risers[0]["name"], n=risers[0]["rank_change"])
        if risers else I["mover_none"]
    )
    # 品类若全是"总榜"，不写"X 类别占比最高"这种无信息量的话
    top_genre_disp = C.genre_label(top_genre, lang)
    genre_phrase = (
        I["genre"].format(genre=top_genre_disp, n=top_genre_n, total=n)
        if top_genre and top_genre_n < n else ""
    )
    dev_phrase = I["dev"].format(dev=top_dev or "—", n=top_dev_n)
    top_phrase = I["top"].format(name=top.get("name", "—"), rating=top.get("rating", "—"))
    insight = I["frame"].format(
        date=date, new=new_phrase, mkt=mkt, ch=ch, n=n,
        mover=mover_phrase, dev=dev_phrase, genre=genre_phrase, top=top_phrase,
    )
    return {
        "insight": insight,
        "new_count": len(new_apps),
        "risers": risers,
        "fallers": fallers,
        "top_dev": top_dev, "top_dev_n": top_dev_n,
        "top_genre": top_genre, "top_genre_n": top_genre_n,
        "longest_streak": longest,
    }

# ---------------------------------------------------------------------------
# SVG 趋势图（服务端生成，无第三方库）
# ---------------------------------------------------------------------------
def trend_svg(series: list[dict], width: int = 640, height: int = 180, uid: str = "t") -> str:
    """series: [{date, best_rank, name}, ...]，排名越小越靠前（y 轴反转）。
    带渐变面积、网格线与端点标记的现代化图表。uid 保证多图 defs id 唯一。"""
    if not series:
        return ""
    pts = []
    n = len(series)
    top_pad, bot_pad = 16, 26
    for i, p in enumerate(series):
        x = 14 + i * (width - 28) / max(n - 1, 1)
        rank = min(p.get("best_rank") or 30, 30)
        y = top_pad + (rank - 1) / 29 * (height - top_pad - bot_pad)
        pts.append((x, y))
    polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    line_path = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area_path = line_path + f" L {pts[-1][0]:.1f},{height-bot_pad} L {pts[0][0]:.1f},{height-bot_pad} Z"
    first = html.escape(str(series[0].get("date", "")))
    last = html.escape(str(series[-1].get("date", "")))
    fx, fy = pts[0]
    lx, ly = pts[-1]
    grid = ""
    for g in (8, 16, 24):
        gy = top_pad + g / 29 * (height - top_pad - bot_pad)
        grid += (f'<line x1="14" y1="{gy:.1f}" x2="{width-14}" y2="{gy:.1f}" '
                 f'stroke="#eef1f6" stroke-width="1" stroke-dasharray="3 4"/>')
    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Rank history from {first} to {last}" class="spark-svg">'
        f'<defs><linearGradient id="fill-{uid}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="#4f46e5" stop-opacity="0.28"/>'
        f'<stop offset="100%" stop-color="#4f46e5" stop-opacity="0.02"/>'
        f'</linearGradient></defs>'
        f'{grid}'
        f'<path d="{area_path}" fill="url(#fill-{uid})"/>'
        f'<path d="{line_path}" fill="none" stroke="#4f46e5" stroke-width="2.5" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
        f'<circle cx="{fx:.1f}" cy="{fy:.1f}" r="3.5" fill="#fff" stroke="#4f46e5" stroke-width="2"/>'
        f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="4" fill="#4f46e5" stroke="#fff" stroke-width="2"/>'
        f'<text x="14" y="{height-7}" font-size="11" fill="#8b93a3">{first}</text>'
        f'<text x="{width-14}" y="{height-7}" font-size="11" fill="#8b93a3" text-anchor="end">{last}</text>'
        f'</svg>'
    )

# ---------------------------------------------------------------------------
# JSON-LD —— 与可见内容一致
# ---------------------------------------------------------------------------
def dataset_schema(rows: list[dict], date: str, market: str, chart: str, lang: str) -> dict:
    name = f"{C.CHARTS[chart][lang]} in {C.market_name(market, lang)} — {date} Snapshot"
    desc = (
        f"Daily snapshot of the {C.CHARTS[chart][lang]} Top 30 in {C.market_name(market, lang)}. "
        f"Rankings are sourced from Apple App Store / Google Play official charts via "
        f"the e-hai/Appstore_Top_30 open dataset, sampled at {date}. "
        f"Ratings and developer data are shown as provided by the source. "
        f"Rank positions reflect a point-in-time sample, not real-time placement."
    )
    return {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": name,
        "description": desc[:5000],
        "creator": {"@type": "Organization", "name": C.SITE["name"]},
        "temporalCoverage": date,
        "spatialCoverage": C.market_name(market, lang),
        "isAccessibleForFree": True,
        "sameAs": f"{C.API_BASE}/rankings/{C.STORES['app_store']['en']}_{market}_{chart}_{date}.json",
    }

def breadcrumb_schema(url: str, name: str, lang: str) -> dict:
    """首页 → 当前榜单页的两级面包屑，帮助搜索引擎理解层级。"""
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "AppRank Index", "item": home_url(lang)},
            {"@type": "ListItem", "position": 2, "name": name, "item": url},
        ],
    }


def itemlist_schema(rows: list[dict], name: str, url: str) -> dict:
    """榜单前 10 名的有序 ItemList；应用详情页尚未上线，因此只给名称与位次。"""
    els = [{"@type": "ListItem", "position": i, "name": r.get("name", "")}
           for i, r in enumerate(rows[:10], 1)]
    return {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": name,
        "url": url,
        "numberOfItems": len(els),
        "itemListOrder": "https://schema.org/ItemListOrderAscending",
        "itemListElement": els,
    }


def related_block(lang: str, store: str, market: str, chart: str,
                  genre: str | None, lang_pages: dict[str, set[str]]) -> str:
    """页内导航：同市场其他榜单、同榜单其他市场、另一商店的同名榜单。
    只链接本语言真实存在的页面，避免死链。"""
    T = L.get(lang)
    existing = {u.rstrip("/") for u in lang_pages.get(lang, set())}

    def link(label: str, url: str) -> str:
        if url.rstrip("/") not in existing:
            return ""
        return f'<a class="chart-link" href="{html.escape(url)}">{html.escape(label)}</a>'

    same_market = []
    for ch2 in C.ALL_CHARTS:
        if ch2 != chart:
            same_market.append(link(C.CHARTS[ch2][lang], page_url(lang, store, market, ch2, None)))
    if store in C.GENRE_BY_STORE:
        g = C.GENRE_BY_STORE[store]
        for ch2 in C.ALL_CHARTS:
            same_market.append(link(f'{C.CHARTS[ch2][lang]} · {C.genre_label("游戏", lang)}',
                                    page_url(lang, store, market, ch2, g)))

    markets = C.ALL_MARKETS if lang == "en" else L.LANG_MARKETS.get(lang, C.ALL_MARKETS)
    other_markets = [link(C.market_name(m, lang), page_url(lang, store, m, chart, genre))
                     for m in markets if m != market]
    other_markets = [a for a in other_markets if a][:12]  # 与首页矩阵互链，这里只放最近 12 个避免页面杂乱

    other_store = ""
    other = "play" if store == "app_store" else "app_store"
    if other in C.ALL_STORES:
        other_name = C.STORES[other].get(lang) or C.STORES[other]["en"]
        other_store = link(f'{other_name} · {C.CHARTS[chart][lang]}',
                           page_url(lang, other, market, chart, genre))

    groups = [(T["rel_same_market"], same_market, ""),
              (T["rel_other_markets"], other_markets, T["rel_home"]),
              (T.get("rel_other_store"), [other_store], "")]
    bits = []
    for label, anchors, tail in groups:
        anchors = [a for a in anchors if a]
        if not anchors:
            continue
        tail_html = f'<a class="chart-link" href="{html.escape(home_url(lang))}">{html.escape(tail)}</a>' if tail else ""
        bits.append(f'<div class="rel-group"><span class="rel-k">{html.escape(label)}</span>'
                    f'<div class="rel-links">{"".join(anchors)}{tail_html}</div></div>')
    if not bits:
        return ""
    return (f'<section class="panel related"><h2>{html.escape(T["rel_title"])}</h2>'
            + "".join(bits) + "</section>")


def software_schema(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows[:3]:  # 仅为可见的前 3 名生成，避免 schema 与可见内容不一致
        s = {
            "@context": "https://schema.org",
            "@type": "MobileApplication",
            "name": r.get("name", ""),
            "applicationCategory": "GameApplication" if r.get("genre_name") in ("游戏", "Games") else "UtilitiesApplication",
        }
        price = r.get("price_amount")
        s["offers"] = {"@type": "Offer", "price": float(price) if price is not None else 0,
                       "priceCurrency": r.get("price_currency") or "USD"}
        # aggregateRating 仅在真的有评分数据时加（须页面可见）
        if r.get("rating") is not None and r.get("rating_count"):
            s["aggregateRating"] = {
                "@type": "AggregateRating",
                "ratingValue": float(r["rating"]),
                "ratingCount": int(r["rating_count"]),
            }
        out.append(s)
    return out

# ---------------------------------------------------------------------------
# 多语言 URL / 语言切换器
# ---------------------------------------------------------------------------
def lang_prefix(lang: str) -> str:
    return "" if lang == "en" else f"/{lang}"


def page_rel_dir(lang: str, store: str, market: str, chart: str, genre: str | None) -> str:
    parts = [store, market, "top", chart] + ([genre] if genre else [])
    return f"{lang_prefix(lang)}/{'/'.join(parts)}"


def page_url(lang: str, store: str, market: str, chart: str, genre: str | None) -> str:
    return f"{C.SITE['base_url']}{page_rel_dir(lang, store, market, chart, genre)}/"


def home_url(lang: str) -> str:
    p = lang_prefix(lang)
    return f"{C.SITE['base_url']}{p}/"


def language_nav(current: str, store: str, market: str, chart: str,
                 genre: str | None, lang_pages: dict[str, set[str]]) -> str:
    """生成语言切换器：链接到同一内容的各语言版本；该语言无此市场页则回落到首页。"""
    links = []
    for code in ["en"] + L.NON_EN_LANGS:
        meta = L.get(code)
        equivalent = page_url(code, store, market, chart, genre)
        if equivalent in lang_pages.get(code, set()):
            href = equivalent
            partial = ""
        else:
            href = home_url(code)  # 该语言没有此市场页面，避免死链
            # 明确告诉用户：这个语言版本只覆盖本地市场，不是当前页的翻译
            partial = (f' class="alt-partial" title="{html.escape(meta["lang_partial_hint"])}"'
                       ' style="opacity:.62" data-partial="1"')
        cur = ' class="current" aria-current="page"' if code == current else ""
        label = meta["native"] if code != "en" else "English"
        marker = '<span aria-hidden="true" style="font-size:.66em;vertical-align:super">*</span>' if partial else ""
        cls = cur if not partial else partial
        links.append(f'<a href="{html.escape(href)}"{cls} lang="{meta["html_lang"]}">{html.escape(label)}{marker}</a>')
    return "\n".join(links)


# ---------------------------------------------------------------------------
# hreflang 生成 + 校验
# ---------------------------------------------------------------------------
def hreflang_tags(mapping: dict[str, str]) -> tuple[str, dict[str, str]]:
    """生成自引用 + 双向互指 + x-default 的 hreflang 标签组。
    mapping: {hreflang_code: full_url} —— 同一内容组（同 chart/品类）在各语言/市场的 URL。
    只有实际生成的页面才进入互指集合，避免指向不存在页面。
    返回 (HTML 标签串, {lang_code: url} 映射) 供校验使用。"""
    out = dict(mapping)
    tags = "\n".join(
        f'    <link rel="alternate" hreflang="{html.escape(code)}" href="{html.escape(url)}"/>'
        for code, url in out.items()
    )
    return tags, out

def validate_hreflang(groups: dict[str, dict[str, str]]) -> list[str]:
    """校验双向互指与自引用。
    groups: {url: {lang_code: target_url}} —— 每个页面声明的 hreflang→URL 映射。
    检查：① 页面 URL 必须出现在自己的映射值里（自引用）
          ② 若 A 声明了 B 的 URL，B 也必须声明 A 的 URL（双向）
          ③ 必须包含 x-default
    """
    errors = []
    for url, mapping in groups.items():
        if url not in mapping.values():
            errors.append(f"[self-ref] {url} not in its own hreflang set")
        if "x-default" not in mapping:
            errors.append(f"[x-default] {url} missing x-default")
    # 双向互指：建立 url -> set(urls it points to)
    for a, map_a in groups.items():
        for target in map_a.values():
            if target in groups and a not in groups[target].values():
                errors.append(f"[bidirectional] {a} -> {target} but not reciprocated")
    return errors

# ---------------------------------------------------------------------------
# 页面渲染
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# 共享视觉设计系统 —— CSS 与 JS 均为独立常量，通过 format 占位符注入。
# 好处：CSS/JS 里的大括号无需在模板里转义，且首页与榜单页共用同一套样式。
# ---------------------------------------------------------------------------
STYLE = r"""
:root{
  --bg:#f5f7fb;--surface:#fff;--line:#e8ebf2;--line-soft:#f0f2f7;
  --ink:#0f172a;--ink-2:#334155;--muted:#64748b;--muted-2:#94a3b8;
  --accent:#4f46e5;--accent-2:#7c3aed;--accent-soft:#eef2ff;
  --up:#059669;--up-soft:#ecfdf5;--down:#e11d48;--down-soft:#fff1f2;
  --new:#2563eb;--new-soft:#eff6ff;--warn:#b45309;--warn-soft:#fffbeb;
  --radius:16px;--radius-sm:10px;
  --shadow:0 1px 2px rgba(15,23,42,.04),0 8px 28px rgba(15,23,42,.05);
  --shadow-lg:0 12px 40px rgba(15,23,42,.10);
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{
  margin:0;font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
  color:var(--ink-2);background:var(--bg);-webkit-font-smoothing:antialiased;
}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.wrap{max-width:1120px;margin:0 auto;padding:0 22px}
h1,h2,h3{color:var(--ink);letter-spacing:-.02em}

/* Top bar */
.topbar{background:#0f172a;color:#fff;border-bottom:1px solid #1e293b}
.topbar .wrap{display:flex;align-items:center;justify-content:space-between;gap:16px;min-height:62px;flex-wrap:wrap}
.brand{display:inline-flex;align-items:center;gap:10px;color:#fff;font-weight:700;font-size:1.05rem;letter-spacing:-.02em}
.brand:hover{text-decoration:none;color:#fff}
.brand-ico{display:grid;place-items:center;width:32px;height:32px;border-radius:9px;
  background:linear-gradient(135deg,var(--accent),var(--accent-2));font-size:1rem;font-weight:800;
  box-shadow:0 4px 14px rgba(79,70,229,.45)}
.brand-dot{color:#a5b4fc}
.crumb{font-size:.84rem;color:#94a3b8}
.crumb a{color:#cbd5e1}
.crumb .sep{margin:0 8px;color:#475569}
.langnav{display:flex;gap:4px;flex-wrap:wrap;align-items:center}
.langnav a{font-size:.76rem;color:#94a3b8;padding:4px 9px;border:1px solid #334155;border-radius:7px;white-space:nowrap}
.langnav a:hover,.langnav a.current{color:#fff;border-color:var(--accent);background:var(--accent);text-decoration:none}
.langflag{display:inline-flex;align-items:center;gap:5px}

/* Hero */
.hero{padding:34px 0 26px}
.hero-eyebrow{display:inline-block;font-size:.72rem;font-weight:700;letter-spacing:.14em;text-transform:uppercase;
  color:var(--accent);background:var(--accent-soft);padding:6px 12px;border-radius:999px;margin-bottom:14px}
.hero h1{font-size:clamp(1.7rem,3.4vw,2.4rem);line-height:1.2;margin:0 0 10px;font-weight:750}
.hero-sub{color:var(--muted);font-size:1rem;margin:0 0 18px;max-width:760px}
.meta-row{display:flex;gap:10px;flex-wrap:wrap}
.meta-pill{display:inline-flex;align-items:center;gap:7px;background:var(--surface);border:1px solid var(--line);
  border-radius:999px;padding:6px 13px;font-size:.8rem;color:var(--muted)}
.meta-pill b{color:var(--ink-2);font-weight:650}
.dot{width:7px;height:7px;border-radius:50%;background:var(--accent);flex:0 0 auto}

/* Insight */
.insight-card{display:flex;gap:16px;align-items:flex-start;background:linear-gradient(135deg,#eef2ff,#faf5ff);
  border:1px solid #e0e7ff;border-radius:var(--radius);padding:18px 20px;margin:6px 0 22px}
.insight-icon{flex:0 0 auto;width:38px;height:38px;border-radius:11px;display:grid;place-items:center;
  background:#fff;color:var(--accent);font-size:1.15rem;box-shadow:var(--shadow)}
.insight-label{font-size:.74rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--accent);margin-bottom:4px}
.insight-card p{margin:0;color:var(--ink-2);font-size:.96rem;line-height:1.65}

/* Stat grid */
.stat-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:24px}
.stat{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius-sm);
  padding:16px 18px;box-shadow:var(--shadow)}
.stat-k{font-size:.72rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted-2)}
.stat-v{font-size:1.3rem;font-weight:750;color:var(--ink);margin-top:7px;line-height:1.25;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.stat-v.accent{color:var(--accent)}
.stat-s{font-size:.78rem;color:var(--muted);margin-top:3px}

/* Panels */
.panel{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);
  box-shadow:var(--shadow);padding:22px;margin-bottom:22px}
.panel-head{display:flex;align-items:flex-end;justify-content:space-between;gap:14px;flex-wrap:wrap;margin-bottom:16px}
.panel h2{font-size:1.22rem;margin:0;font-weight:700}
.panel-sub{color:var(--muted);font-size:.84rem;margin:4px 0 0}
.muted-sm{font-size:.82rem;color:var(--muted-2);font-weight:500;margin-left:8px}
.result-count{font-size:.82rem;color:var(--muted)}
.result-count b{color:var(--accent)}

/* Toolbar */
.toolbar{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin-bottom:14px}
.search{position:relative;flex:1 1 260px}
.search input{width:100%;padding:10px 14px 10px 38px;border:1px solid var(--line);border-radius:var(--radius-sm);
  font-size:.9rem;background:#fbfcfe;color:var(--ink);outline:none;transition:border-color .15s,box-shadow .15s}
.search input:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
.search .ico{position:absolute;left:13px;top:50%;transform:translateY(-50%);color:var(--muted-2);font-size:.95rem}
.segments{display:inline-flex;background:var(--bg);border:1px solid var(--line);border-radius:var(--radius-sm);padding:3px;gap:2px}
.seg{border:0;background:transparent;color:var(--muted);font-size:.82rem;font-weight:600;padding:7px 13px;
  border-radius:7px;cursor:pointer;transition:.15s;white-space:nowrap;font-family:inherit}
.seg:hover{color:var(--ink)}
.seg.active{background:var(--surface);color:var(--accent);box-shadow:var(--shadow)}

/* Table */
.table-scroll{overflow-x:auto;border:1px solid var(--line);border-radius:var(--radius-sm)}
table.rank{width:100%;border-collapse:collapse;font-size:.9rem;min-width:720px}
table.rank thead th{position:sticky;top:0;background:#fafbfe;text-align:left;font-size:.72rem;
  letter-spacing:.07em;text-transform:uppercase;color:var(--muted);font-weight:700;padding:12px 14px;
  border-bottom:1px solid var(--line);cursor:pointer;user-select:none;white-space:nowrap}
table.rank thead th:hover{color:var(--accent)}
table.rank thead th .arrow{color:var(--muted-2);margin-left:4px;font-size:.7rem}
table.rank tbody td{padding:12px 14px;border-bottom:1px solid var(--line-soft);vertical-align:middle}
table.rank tbody tr:last-child td{border-bottom:0}
table.rank tbody tr{transition:background .12s}
table.rank tbody tr:hover{background:#fafbff}
.rk{display:inline-grid;place-items:center;min-width:30px;height:30px;padding:0 6px;border-radius:9px;
  font-weight:700;font-size:.82rem;background:var(--bg);color:var(--muted);font-variant-numeric:tabular-nums}
.rk.gold{background:linear-gradient(135deg,#fbbf24,#f59e0b);color:#fff;box-shadow:0 3px 10px rgba(245,158,11,.35)}
.rk.silver{background:linear-gradient(135deg,#cbd5e1,#94a3b8);color:#fff}
.rk.bronze{background:linear-gradient(135deg,#fdba74,#ea580c);color:#fff}
.app-cell{display:flex;align-items:center;gap:11px}
.app-logo{flex:0 0 auto;width:36px;height:36px;border-radius:10px;display:grid;place-items:center;
  font-weight:750;font-size:.95rem;color:#fff;background:linear-gradient(135deg,var(--accent),var(--accent-2))}
.app-name{font-weight:650;color:var(--ink);line-height:1.3}
.app-dev{font-size:.76rem;color:var(--muted);margin-top:1px}
.genre-pill{display:inline-block;font-size:.75rem;color:var(--accent);background:var(--accent-soft);
  padding:4px 10px;border-radius:999px;font-weight:600}
.rating-cell{white-space:nowrap;font-variant-numeric:tabular-nums;font-weight:600;color:var(--ink-2)}
.star{color:#f59e0b;margin-right:3px}
.move{display:inline-flex;align-items:center;gap:4px;font-size:.8rem;font-weight:700;padding:4px 9px;
  border-radius:999px;font-variant-numeric:tabular-nums;white-space:nowrap}
.move.up{color:var(--up);background:var(--up-soft)}
.move.down{color:var(--down);background:var(--down-soft)}
.move.new{color:var(--new);background:var(--new-soft)}
.move.flat{color:var(--muted-2);background:var(--bg)}
.empty-row td{text-align:center;color:var(--muted);padding:36px}

/* Matrix directory table (homepage) */
table.matrix{width:100%;border-collapse:collapse;font-size:.84rem;min-width:680px}
table.matrix thead th{background:#fafbfe;color:var(--muted);font-size:.72rem;letter-spacing:.06em;
  text-transform:uppercase;font-weight:700;padding:12px 14px;text-align:left;border-bottom:1px solid var(--line)}
table.matrix tbody td{border-bottom:1px solid var(--line-soft);padding:10px 14px}
table.matrix tbody tr:hover{background:#fafbff}
table.matrix td.mkt{font-weight:650;color:var(--ink);white-space:nowrap;position:sticky;left:0;background:#fff}
.chart-link{display:inline-block;font-size:.78rem;font-weight:600;color:var(--accent);
  background:var(--accent-soft);padding:3px 9px;border-radius:7px;white-space:nowrap}
.chart-link:hover{background:var(--accent);color:#fff;text-decoration:none}
.rel-group{margin-top:14px}
.rel-k{display:block;font-size:.72rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--muted-2);margin-bottom:8px}
.rel-links{display:flex;flex-wrap:wrap;gap:8px}
.dash{color:#cbd5e1}

/* Spark grid */
.spark-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}
.spark-card{background:linear-gradient(180deg,#fcfdff,#fff);border:1px solid var(--line);border-radius:var(--radius-sm);padding:14px 16px}
.spark-card h3{font-size:.92rem;margin:0 0 2px;font-weight:650}
.spark-meta{font-size:.76rem;color:var(--muted);margin:0 0 8px}
.spark-svg{width:100%;height:auto;display:block;border-radius:8px}

/* Two column */
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:22px}
.two-col .panel{margin-bottom:22px}
.prose p{color:var(--ink-2);margin:0;font-size:.92rem;line-height:1.7}
details{border-bottom:1px solid var(--line-soft)}
details:last-child{border-bottom:0}
summary{cursor:pointer;padding:11px 0;font-weight:650;font-size:.9rem;color:var(--ink);list-style:none;
  display:flex;align-items:center;justify-content:space-between;gap:12px}
summary::-webkit-details-marker{display:none}
summary::after{content:"+";color:var(--accent);font-size:1.1rem;font-weight:500;flex:0 0 auto}
details[open] summary::after{content:"\2212"}
details p{margin:0 0 12px;color:var(--muted);font-size:.86rem;line-height:1.6}

/* Footer */
footer{background:#0f172a;color:#94a3b8;padding:28px 0 34px;font-size:.82rem;line-height:1.7}
footer .wrap{max-width:1120px}
footer a{color:#a5b4fc}
footer p{margin:5px 0}
.footer-brand{color:#fff;font-weight:700;font-size:.95rem;margin-bottom:8px}

/* Responsive */
@media(max-width:900px){
  .stat-grid{grid-template-columns:repeat(2,1fr)}
  .two-col{grid-template-columns:1fr}
}
@media(max-width:560px){
  .wrap{padding:0 15px}
  .topbar .wrap{min-height:56px}
  .crumb{font-size:.76rem}
  .hero{padding:24px 0 20px}
  .hero h1{font-size:1.5rem}
  .stat-grid{gap:10px}
  .stat{padding:13px 14px}
  .stat-v{font-size:1.1rem}
  .panel{padding:16px}
  .insight-card{padding:15px}
  .segments{width:100%;overflow-x:auto}
}
"""

# JS 逻辑独立成串，用 __ROWS_JSON__ 等占位；注入后大括号不会被再次 format 解析。
APP_JS = r"""
const ROWS=__ROWS_JSON__;
const STR={empty:__S_EMPTY__,count:__S_COUNT__,new:__S_NEW__,
           segAll:__S_SEGALL__,segUp:__S_SEGUP__,segDown:__S_SEGDOWN__,segNew:__S_SEGNEW__};
let sortKey='rank',sortDir=1,activeFilter='all';
function esc(s){const d=document.createElement('div');d.textContent=(s==null?'':String(s));return d.innerHTML;}
function initial(s){return esc((s||'?').trim().charAt(0).toUpperCase());}
function rankHtml(n){
  const cls=n===1?'gold':n===2?'silver':n===3?'bronze':'';
  return '<span class="rk '+cls+'">'+n+'</span>';
}
function moveHtml(r){
  if(r.status==='new')return '<span class="move new">'+esc(STR.new)+'</span>';
  const c=r.rank_change||0;
  if(c>0)return '<span class="move up">\u25B2 +'+c+'</span>';
  if(c<0)return '<span class="move down">\u25BC '+c+'</span>';
  return '<span class="move flat">\u2014</span>';
}
function ratingHtml(r){
  if(r.rating==null)return '<span style="color:#94a3b8">\u2014</span>';
  return '<span class="rating-cell"><span class="star">\u2605</span>'+esc(r.rating)+'</span>';
}
function sortBy(k){
  if(sortKey===k){sortDir=-sortDir;}else{sortKey=k;sortDir=(k==='rank'||k==='name'||k==='developer'||k==='category')?1:-1;}
  document.querySelectorAll('th[data-k]').forEach(th=>{
    const a=th.querySelector('.arrow');
    if(a)a.textContent=(th.dataset.k===sortKey)?(sortDir>0?'\u25B2':'\u25BC'):'';
  });
  render();
}
function setFilter(f,el){
  activeFilter=f;
  document.querySelectorAll('.seg').forEach(b=>b.classList.toggle('active',b===el));
  render();
}
function render(){
  const q=document.getElementById('q').value.toLowerCase();
  let rs=ROWS.filter(r=>{
    const m=(r.name+' '+r.developer).toLowerCase().includes(q);
    const c=activeFilter==='all'||
      (activeFilter==='up'&&(r.rank_change||0)>0)||
      (activeFilter==='down'&&(r.rank_change||0)<0)||
      (activeFilter==='new'&&r.status==='new');
    return m&&c;
  });
  rs.sort((a,b)=>{
    let va,vb;
    if(sortKey==='change'){va=a.rank_change||0;vb=b.rank_change||0;}
    else if(sortKey==='rating'){va=a.rating==null?-1:a.rating;vb=b.rating==null?-1:b.rating;}
    else{va=a[sortKey]||'';vb=b[sortKey]||'';}
    if(va<vb)return -1*sortDir;
    if(va>vb)return 1*sortDir;
    return 0;
  });
  document.getElementById('tb').innerHTML=rs.map(r=>
    '<tr><td>'+rankHtml(r.curr_rank)+'</td>'+
    '<td><div class="app-cell"><span class="app-logo">'+initial(r.name)+'</span><div>'+
      '<div class="app-name">'+esc(r.name)+'</div><div class="app-dev">'+esc(r.developer)+'</div></div></div></td>'+
    '<td>'+esc(r.developer)+'</td>'+
    '<td><span class="genre-pill">'+esc(r.genre_name||'\u2014')+'</span></td>'+
    '<td>'+ratingHtml(r)+'</td>'+
    '<td>'+moveHtml(r)+'</td></tr>'
  ).join('')||'<tr class="empty-row"><td colspan="6">'+esc(STR.empty)+'</td></tr>';
  document.getElementById('count').innerHTML=STR.count.replace('{a}',rs.length).replace('{b}',ROWS.length);
}
render();
"""

TPL = """<!doctype html>
<html lang="{html_lang}">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{title}</title>
<meta name="description" content="{description}"/>
<meta name="robots" content="index,follow"/>
<link rel="canonical" href="{canonical}"/>
{hreflang}
<script type="application/ld+json">{jsonld}</script>
<style>{style}</style>
</head>
<body>
<header class="topbar"><div class="wrap">
  <a class="brand" href="{home_url}"><span class="brand-ico">A</span><span>AppRank<span class="brand-dot">.</span>Index</span></a>
  <nav class="langnav" aria-label="{lang_label}">{lang_nav}</nav>
</div></header>

<main class="wrap">
  <section class="hero">
    <span class="hero-eyebrow">{hero_eyebrow} \u00b7 {mkt} \u00b7 {ch}</span>
    <h1>{h1}</h1>
    <p class="hero-sub">{hero_sub}</p>
    <div class="meta-row">
      <span class="meta-pill"><span class="dot"></span>{meta_updated} <b>{updated}</b></span>
      <span class="meta-pill"><span class="dot"></span>{meta_source} <b>{source_note}</b></span>
      {streak_note}
    </div>
  </section>

  <section class="insight-card">
    <div class="insight-icon">\u2726</div>
    <div><div class="insight-label">{insight_label}</div><p>{insight}</p></div>
  </section>

  <div class="stat-grid">{stats}</div>

  <section class="panel">
    <div class="panel-head">
      <div><h2>{tbl_title}</h2><p class="panel-sub">{tbl_sub}</p></div>
      <span class="result-count" id="count"></span>
    </div>
    <div class="toolbar">
      <label class="search"><span class="ico">\u26b2</span>
        <input id="q" type="search" placeholder="{search_ph}" oninput="render()"/></label>
      <div class="segments">
        <button class="seg active" data-f="all" onclick="setFilter('all',this)">{seg_all}</button>
        <button class="seg" data-f="up" onclick="setFilter('up',this)">{seg_up}</button>
        <button class="seg" data-f="down" onclick="setFilter('down',this)">{seg_down}</button>
        <button class="seg" data-f="new" onclick="setFilter('new',this)">{seg_new}</button>
      </div>
    </div>
    <div class="table-scroll">
      <table class="rank"><thead><tr>
        <th data-k="rank" onclick="sortBy('rank')">{th_rank}<span class="arrow"></span></th>
        <th data-k="name" onclick="sortBy('name')">{th_app}<span class="arrow"></span></th>
        <th data-k="developer" onclick="sortBy('developer')">{th_dev}<span class="arrow"></span></th>
        <th data-k="category" onclick="sortBy('category')">{th_cat}<span class="arrow"></span></th>
        <th data-k="rating" onclick="sortBy('rating')">{th_rating}<span class="arrow"></span></th>
        <th data-k="change" onclick="sortBy('change')">{th_move}<span class="arrow"></span></th>
      </tr></thead><tbody id="tb"></tbody></table>
    </div>
  </section>

  <section class="panel">
    <h2>{rank_title} <span class="muted-sm">{rank_sub}</span></h2>
    <div class="spark-grid">{spark}</div>
  </section>

  {related}

  <div class="two-col">
    <section class="panel prose"><h2>{method_title}</h2><p>{methodology}</p></section>
    <section class="panel"><h2>{faq_title}</h2>{faq}</section>
  </div>
</main>

<footer><div class="wrap">
  <div class="footer-brand">AppRank<span class="brand-dot">.</span>Index</div>
  <p>{attribution}</p>
  <p>{footer_note}</p>
</div></footer>
<script>{app_js}</script>
</body>
</html>
"""

def render_page(lang, store, market, chart, date, genre, rows, trend, insights,
                hreflang_mapping, lang_pages, out_root):
    T = L.get(lang)
    mkt = C.market_name(market, lang)
    ch = C.CHARTS[chart][lang]
    gn = C.genre_label("游戏", lang) if genre else None  # 品类页当前仅"游戏"
    h1 = T["h1_chart"].format(ch=ch, mkt=mkt, date=date) + (f" ({gn})" if gn else "")
    title = T["title_chart"].format(ch=ch, mkt=mkt, date=date, site=C.SITE["name"])
    description = make_description(insights["insight"])

    rel_dir = page_rel_dir(lang, store, market, chart, genre)
    url = page_url(lang, store, market, chart, genre)
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    source_note = "App Store" if store == "app_store" else "Google Play"
    methodology = T["methodology"].format(ch=ch, mkt=mkt, date=date)
    streak_note = (
        f'<span class="meta-pill"><span class="dot"></span>'
        f'{html.escape(T["meta_longest_streak"])} <b>{insights["longest_streak"]} '
        f'{html.escape(T["days"])}</b></span>'
        if insights['longest_streak'] else ""
    )

    # 统计卡片：由当日真实数据计算，文案随语言变化
    top = rows[0] if rows else {}
    risers = insights.get("risers") or []
    biggest = risers[0] if risers else None
    def stat(k, v, s="", accent=False):
        vc = " accent" if accent else ""
        return (f'<div class="stat"><div class="stat-k">{html.escape(k)}</div>'
                f'<div class="stat-v{vc}" title="{html.escape(str(v))}">{html.escape(str(v))}</div>'
                + (f'<div class="stat-s">{html.escape(str(s))}</div>' if s else "") + '</div>')
    stats = "".join([
        stat(T["stat_1"], top.get("name", "—"), f'{ch} · {mkt}', accent=True),
        stat(T["stat_2"], str(insights["new_count"]), T["stat_2_sub"]),
        stat(T["stat_3"], biggest["name"] if biggest else "—",
             (f'+{biggest["rank_change"]} {T["stat_spots"]}' if biggest else T["stat_3_none"])),
        stat(T["stat_4"], insights["top_dev"] or "—",
             f'{insights["top_dev_n"]} {T["stat_apps_board"]}'),
    ])

    # 趋势 SVG：取前 5 名中在趋势里有数据的
    spark_parts = []
    trend_map = trend.get("trends", {})
    for i, r in enumerate(rows[:5]):
        s = trend_map.get(r.get("app_id"), [])
        if s:
            recent = s[-30:]
            spark_parts.append(
                f'<div class="spark-card"><h3>{html.escape(r["name"])}</h3>'
                f'<p class="spark-meta">{html.escape(T["best_over"].format(n=len(recent)))}</p>'
                f'{trend_svg(recent, uid=f"{lang}-c{i}")}</div>'
            )
    spark = ("\n".join(spark_parts) or
             f'<p class="muted-sm">{html.escape(T["empty"])}</p>')

    faq = "".join(
        f'<details><summary>{html.escape(q)}</summary><p>{html.escape(a)}</p></details>'
        for q, a in T["faq"]
    )

    attribution = (
        f'{html.escape(T["footer_source_prefix"])} '
        '<a href="https://github.com/e-hai/Appstore_Top_30" rel="nofollow">e-hai/Appstore_Top_30</a> '
        f'— {html.escape(T["footer_tm"])}'
    )
    footer_note = html.escape(T["footer_note"].format(updated=updated))

    hl, hl_map = hreflang_tags(hreflang_mapping)
    crumb_name = f"{ch} · {mkt}" + (f" · {gn}" if gn else "")
    jsonld = json.dumps([dataset_schema(rows, date, market, chart, lang)]
                        + software_schema(rows)
                        + [breadcrumb_schema(url, crumb_name, lang),
                           itemlist_schema(rows, f"{ch} · {mkt} · {date}", url)],
                        ensure_ascii=False)
    related = related_block(lang, store, market, chart, genre, lang_pages)

    # 语言切换器：当前页在各语言是否有对应页
    nav = language_nav(lang, store, market, chart, genre, lang_pages)

    # 给 JS 的精简行数据
    js_rows = [{
        "curr_rank": r.get("curr_rank"), "name": r.get("name", ""),
        "developer": r.get("developer", ""),
        "genre_name": C.genre_label(r.get("genre_name", ""), lang),
        "rating": r.get("rating"), "rank_change": r.get("rank_change") or 0,
        "status": r.get("status", ""),
    } for r in rows]

    app_js = (APP_JS
              .replace("__ROWS_JSON__", json.dumps(js_rows, ensure_ascii=False))
              .replace("__S_EMPTY__", json.dumps(T["empty"], ensure_ascii=False))
              .replace("__S_COUNT__", json.dumps(T["count_fmt"], ensure_ascii=False))
              .replace("__S_NEW__", json.dumps(T["seg_new"], ensure_ascii=False))
              .replace("__S_SEGALL__", json.dumps(T["seg_all"], ensure_ascii=False))
              .replace("__S_SEGUP__", json.dumps(T["seg_up"], ensure_ascii=False))
              .replace("__S_SEGDOWN__", json.dumps(T["seg_down"], ensure_ascii=False))
              .replace("__S_SEGNEW__", json.dumps(T["seg_new"], ensure_ascii=False)))

    page = TPL.format(
        html_lang=T["html_lang"], title=html.escape(title), description=html.escape(description),
        canonical=url, hreflang=hl, jsonld=jsonld, style=STYLE, app_js=app_js,
        home_url=home_url(lang), lang_label=html.escape(T["lang_label"]), lang_nav=nav,
        hero_eyebrow=html.escape(T["hero_eyebrow_chart"]),
        hero_sub=html.escape(T["hero_sub_chart"]),
        meta_updated=html.escape(T["meta_last_updated"]),
        meta_source=html.escape(T["meta_source"]),
        h1=html.escape(h1), mkt=html.escape(mkt), ch=html.escape(ch),
        updated=updated, source_note=html.escape(source_note), streak_note=streak_note,
        insight_label=html.escape(T["insight_label"]),
        insight=html.escape(insights["insight"]), tbl_title=html.escape(T["tbl_title"]),
        tbl_sub=html.escape(T["tbl_sub"]), search_ph=html.escape(T["search_ph"]),
        seg_all=html.escape(T["seg_all"]), seg_up=html.escape(T["seg_up"]),
        seg_down=html.escape(T["seg_down"]), seg_new=html.escape(T["seg_new"]),
        th_rank=html.escape(T["th_rank"]), th_app=html.escape(T["th_app"]),
        th_dev=html.escape(T["th_developer"]), th_cat=html.escape(T["th_category"]),
        th_rating=html.escape(T["th_rating"]), th_move=html.escape(T["th_move"]),
        rank_title=html.escape(T["rank_title"]), rank_sub=html.escape(T["rank_sub"]),
        method_title=html.escape(T["method_title"]), methodology=html.escape(methodology),
        faq_title=html.escape(T["faq_title"]), faq=faq,
        attribution=attribution, footer_note=footer_note,
        stats=stats, spark=spark, related=related,
    )
    dest = Path(out_root) / rel_dir.lstrip("/") / "index.html"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(page, encoding="utf-8")
    return str(dest), url, hl_map

# ---------------------------------------------------------------------------
# Sitemap
# ---------------------------------------------------------------------------
def write_homepage(lang, urls: list[tuple[str, str]], out_root: str, date: str):
    """生成该语言的导航枢纽首页。英文在 /，其他语言在 /{lang}/。
    只输出本语言实际存在的页面链接（urls 来自本轮 fetch 结果），避免死链。"""
    T = L.get(lang)
    base = C.SITE["base_url"].rstrip("/")
    existing = {u.rstrip("/") for u, _ in urls}
    markets = L.LANG_MARKETS.get(lang, C.ALL_MARKETS) if lang != "en" else C.ALL_MARKETS

    def cell(store, m, ch, g=None):
        url = page_url(lang, store, m, ch, g)
        if url.rstrip("/") not in existing:
            return '<span class="dash">—</span>'
        label = C.CHARTS[ch][lang] + (f" · {C.genre_label('游戏', lang)}" if g else "")
        return f'<a class="chart-link" href="{html.escape(url)}">{html.escape(label)}</a>'

    n = len(existing)
    desc = (f"Daily Top 30 app charts for {len(markets)} markets across the App Store and "
            f"Google Play: free, paid, grossing and games, with rank history and insights. "
            f"Snapshot {date}.")

    store_panels = []
    for s in C.ALL_STORES:
        platform_table_rows = []
        genre = C.GENRE_BY_STORE.get(s)
        head = (f"<tr><th>{html.escape(T['mx_market'])}</th><th>{html.escape(T['mx_free'])}</th>"
                f"<th>{html.escape(T['mx_paid'])}</th><th>{html.escape(T['mx_grossing'])}</th>"
                f"<th>{html.escape(T['mx_gfree'])}</th><th>{html.escape(T['mx_gpaid'])}</th>"
                f"<th>{html.escape(T['mx_ggrossing'])}</th></tr>")
        for m in markets:
            cells = [f'<td class="mkt">{html.escape(C.market_name(m, lang))}</td>']
            cells += [f"<td>{cell(s, m, ch)}</td>" for ch in C.ALL_CHARTS]
            cells += [f"<td>{cell(s, m, ch, genre) if genre else '—'}</td>" for ch in C.ALL_CHARTS]
            platform_table_rows.append("<tr>" + "".join(cells) + "</tr>")
        store_panels.append(
            f'<section class="panel"><div class="panel-head"><div>'
            f'<h2>{html.escape(C.STORES[s]["en"])}</h2>'
            f'<p class="panel-sub">{html.escape(T["browse_sub"])}</p>'
            f'</div></div><div class="table-scroll"><table class="matrix">{head}'
            f'{"".join(platform_table_rows)}</table></div></section>')

    stat_grid = "".join([
        f'<div class="stat"><div class="stat-k">{html.escape(T["stat_markets"])}</div>'
        f'<div class="stat-v accent">{len(markets)}</div>'
        f'<div class="stat-s">{html.escape(T["stat_markets_sub"])}</div></div>',
        f'<div class="stat"><div class="stat-k">{html.escape(T["stat_pages"])}</div>'
        f'<div class="stat-v">{n}</div><div class="stat-s">{T["stat_pages_sub"]}</div></div>',
        f'<div class="stat"><div class="stat-k">{html.escape(T["stat_platforms"])}</div>'
        f'<div class="stat-v">2</div><div class="stat-s">{T["stat_platforms_sub"]}</div></div>',
        f'<div class="stat"><div class="stat-k">{html.escape(T["stat_snapshot"])}</div>'
        f'<div class="stat-v" style="font-size:1.05rem">{html.escape(date)}</div>'
        f'<div class="stat-s">{html.escape(T["stat_snapshot_sub"])}</div></div>',
    ])
    store_panels_html = "\n".join(store_panels)
    # 首页语言切换：各语言首页始终存在
    nav_links = []
    for code in ["en"] + L.NON_EN_LANGS:
        meta = L.get(code)
        cur = ' class="current" aria-current="page"' if code == lang else ""
        label = "English" if code == "en" else meta["native"]
        nav_links.append(f'<a href="{html.escape(home_url(code))}"{cur} '
                         f'lang="{meta["html_lang"]}">{html.escape(label)}</a>')
    nav = "\n".join(nav_links)

    hreflang_home = "\n".join(
        f'    <link rel="alternate" hreflang="{"x-default" if c == "en" else c}" '
        f'href="{html.escape(home_url(c))}"/>'
        for c in ["en"] + L.NON_EN_LANGS
    )
    page = f"""<!doctype html>
<html lang="{T['html_lang']}">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{html.escape(C.SITE['name'])} — {html.escape(T['home_title'])}</title>
<meta name="description" content="{html.escape(desc)}"/>
<meta name="robots" content="index,follow"/>
<link rel="canonical" href="{html.escape(home_url(lang))}"/>
{hreflang_home}
<script type="application/ld+json">{{
  "@context":"https://schema.org","@type":"Dataset",
  "name":"{html.escape(C.SITE['name'])} — Daily App Charts",
  "description":"{html.escape(desc)}",
  "creator":{{"@type":"Organization","name":"{html.escape(C.SITE['name'])}"}},
  "temporalCoverage":"{date}","isAccessibleForFree":true,
  "sameAs":"https://e-hai.github.io/Appstore_Top_30/api/"
}}</script>
<style>{STYLE}</style>
</head>
<body>
<header class="topbar"><div class="wrap">
  <a class="brand" href="{html.escape(home_url(lang))}"><span class="brand-ico">A</span><span>AppRank<span class="brand-dot">.</span>Index</span></a>
  <nav class="langnav" aria-label="{html.escape(T['lang_label'])}">{nav}</nav>
</div></header>

<main class="wrap">
  <section class="hero">
    <span class="hero-eyebrow">{html.escape(T['home_eyebrow'])}</span>
    <h1>{html.escape(T['home_title'])}</h1>
    <p class="hero-sub">{html.escape(T['home_sub'].format(n=len(markets)))}</p>
    <div class="meta-row">
      <span class="meta-pill"><span class="dot"></span>{html.escape(T['home_updated'])}</span>
      <span class="meta-pill"><span class="dot"></span>{html.escape(T['home_source_label'])}<b>e-hai/Appstore_Top_30</b></span>
    </div>
  </section>

  <div class="stat-grid">{stat_grid}</div>

  {store_panels_html}
</main>

<footer><div class="wrap">
  <div class="footer-brand">AppRank<span class="brand-dot">.</span>Index</div>
  <p>{html.escape(T['footer_source_prefix'])} <a href="https://github.com/e-hai/Appstore_Top_30" rel="nofollow">e-hai/Appstore_Top_30</a> — {html.escape(T['footer_tm'])}</p>
</div></footer>
</body>
</html>"""
    prefix = lang_prefix(lang).lstrip("/")
    dest = Path(out_root) / prefix / "index.html" if prefix else Path(out_root, "index.html")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(page, encoding="utf-8")
    return str(dest)

def write_sitemap(urls: list[tuple[str, str]], out_root: str):
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
             'xmlns:xhtml="http://www.w3.org/1999/xhtml">']
    for url, updated in urls:
        lines.append(f"  <url><loc>{html.escape(url)}</loc><lastmod>{updated}</lastmod></url>")
    lines.append("</urlset>")
    Path(out_root, "sitemap.xml").write_text("\n".join(lines), encoding="utf-8")

def write_robots(out_root: str):
    Path(out_root, "robots.txt").write_text(
        "User-agent: *\nAllow: /\nSitemap: " + C.SITE["base_url"] + "/sitemap.xml\n",
        encoding="utf-8")


def write_not_found(out_root: str):
    """404 页面：未知路径返回真 404，避免整站软 404。"""
    base = C.SITE["base_url"]
    t = L.get("en")
    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Page not found — AppRank Index</title>
<meta name="description" content="This page does not exist."/>
<meta name="robots" content="noindex,follow"/>
<style>{STYLE}</style>
</head>
<body>
<header class="topbar"><div class="wrap">
  <a class="brand" href="{base}/"><span class="brand-ico">A</span><span>AppRank<span class="brand-dot">.</span>Index</span></a>
  <nav class="langnav" aria-label="Language"><a href="{base}/" aria-current="page">English</a><a href="{base}/ko/">한국어</a><a href="{base}/ja/">日本語</a><a href="{base}/zh/">中文</a><a href="{base}/tr/">Türkçe</a></nav>
</div></header>
<main class="wrap">
  <section class="hero">
    <span class="hero-eyebrow">404</span>
    <h1>That page is not in the directory</h1>
    <p class="hero-sub">The URL you opened does not match any chart. It may have moved, or the market and chart combination was never published.</p>
    <p><a href="{base}/">Browse all 39 markets</a> · <a href="{base}/app_store/us/top/free/">United States · Top Free</a></p>
  </section>
</main>
<footer><div class="wrap">{html.escape(t["footer_note"].split("{")[0].strip())} · {html.escape(C.SITE.get("author", "AppRank Index"))}</div></footer>
</body>
</html>
"""
    Path(out_root, "404.html").write_text(page, encoding="utf-8")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def build_jobs(mode: str):
    """返回需要抓取排名的数据作业: [(store, market, chart, genre)]，按数据组合去重。
    语言维度不在这里展开——同一份排名数据会被多个语言渲染，避免重复网络请求。"""
    if mode == "sample":
        return [("app_store", m, C.PILOT_CHART, g)
                for m in C.PILOT_MARKETS for g in C.PILOT_GENRES][:10]
    if mode == "full":
        jobs = []
        for store in C.ALL_STORES:
            for m in C.ALL_MARKETS:
                for ch in C.ALL_CHARTS:
                    jobs.append((store, m, ch, None))          # 总榜
                    g = C.GENRE_BY_STORE.get(store)
                    if g:
                        jobs.append((store, m, ch, g))         # 游戏榜
        return jobs
    raise ValueError(f"unknown mode: {mode}")


def _langs_for_market(market: str) -> list[str]:
    """该市场需要渲染哪些语言：英文全部 + 覆盖该市场的其他语言。"""
    return ["en"] + [lg for lg, mkts in L.LANG_MARKETS.items() if market in mkts]


def _content_key(store, ch, genre):
    return (store, ch, genre or "total")


def _build_hreflang_maps(mode: str) -> dict[tuple, dict[str, str]]:
    """为每个内容组构建 {hreflang_code: url}。只纳入本轮会实际生成的语言×市场页面。"""
    result: dict[tuple, dict[str, str]] = {}
    markets = C.PILOT_MARKETS if mode == "sample" else C.ALL_MARKETS
    charts = [C.PILOT_CHART] if mode == "sample" else C.ALL_CHARTS
    for store in C.ALL_STORES:
        for ch in charts:
            genres = ([None] + ([C.GENRE_BY_STORE[store]] if store in C.GENRE_BY_STORE else []))
            if mode == "sample":
                genres = list(C.PILOT_GENRES)
            for g in genres:
                key = _content_key(store, ch, g)
                mapping: dict[str, str] = {}
                # 英文：所有市场，按市场 hreflang 码
                for m in markets:
                    mapping[C.hreflang_code(m, "en")] = page_url("en", store, m, ch, g)
                # 其他语言：仅覆盖本语言市场的页面
                for lang in L.NON_EN_LANGS:
                    for m in L.LANG_MARKETS[lang]:
                        if m in markets:
                            mapping[L.hreflang_code(lang, m)] = page_url(lang, store, m, ch, g)
                # x-default 指向英文美国页（若本轮生成 us）
                if "us" in markets:
                    mapping["x-default"] = page_url("en", store, "us", ch, g)
                result[key] = mapping
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="site")
    ap.add_argument("--mode", choices=["sample", "full"], default="sample",
                    help="sample=10页验证; full=全量总榜+游戏榜")
    ap.add_argument("--state", default=".build_state.json", help="增量状态文件")
    ap.add_argument("--no-indexnow", action="store_true", help="跳过 IndexNow 提交（本地测试用）")
    ap.add_argument("--submit-indexnow", action="store_true", help="即使非新数据日也提交变化 URL")
    args = ap.parse_args()

    out = args.out
    Path(out).mkdir(parents=True, exist_ok=True)
    dates = get_latest_dates(1)
    date = dates[0]
    print(f"[i] latest source date: {date}  mode={args.mode}")

    jobs = build_jobs(args.mode)
    print(f"[i] data jobs to fetch: {len(jobs)}")

    # 每个内容组的 hreflang 映射（含语言变体）
    hreflang_by_key = _build_hreflang_maps(args.mode)

    # 每个语言实际生成的页面集合：用于语言切换器判断是否提供对应页。
    # 用"每个内容组里该语言对应的 URL 集合"精确构建，避免与英文页的
    # zh-Hant-XX 码（英文站历史用法）混淆。
    lang_pages: dict[str, set[str]] = {lg: set() for lg in ["en"] + L.NON_EN_LANGS}
    markets_scope = C.PILOT_MARKETS if args.mode == "sample" else C.ALL_MARKETS
    for store in C.ALL_STORES:
        charts = [C.PILOT_CHART] if args.mode == "sample" else C.ALL_CHARTS
        genres = list(C.PILOT_GENRES) if args.mode == "sample" else (
            [None] + ([C.GENRE_BY_STORE[store]] if store in C.GENRE_BY_STORE else []))
        for ch in charts:
            for g in genres:
                for m in markets_scope:
                    lang_pages["en"].add(page_url("en", store, m, ch, g))
                for lg, mkts in L.LANG_MARKETS.items():
                    for m in mkts:
                        if m in markets_scope:
                            lang_pages[lg].add(page_url(lg, store, m, ch, g))

    # 增量状态
    state = INC.load_state(args.state)
    prev_pages: dict[str, str] = state.get("pages", {})
    is_new_day = state.get("date") != date
    print(f"[i] state date={state.get('date')}  is_new_day={is_new_day}")

    # ---- 并发拉取所有 ranking ----
    def fetch_one(job):
        store, market, ch, genre = job
        try:
            return job, get_ranking(store, market, ch, date, genre), None
        except Exception as e:
            return job, None, str(e)

    print(f"[i] fetching {len(jobs)} rankings concurrently...")
    fetched = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
        for job, data, err in ex.map(fetch_one, jobs):
            if err:
                print(f"[ERR] fetch {job}: {err}", file=sys.stderr)
            elif not data.get("rows"):
                print(f"[!] no data: {job}")
            else:
                fetched.append((job, data))
    print(f"[i] fetched {len(fetched)} rankings with data")

    # ---- 并发拉取 trend ----
    trend_keys = sorted({(j[0], j[1], j[2]) for j, _ in fetched})
    trend_cache: dict[str, dict] = {}
    def fetch_trend(tk):
        try:
            return tk, get_trend(*tk), None
        except Exception as e:
            return tk, {"trends": {}}, str(e)
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
        for tk, td, err in ex.map(fetch_trend, trend_keys):
            trend_cache[":".join(tk)] = td
    print(f"[i] fetched {len(trend_cache)} trends")

    # ---- 按语言渲染 ----
    urls_by_lang: dict[str, list[tuple[str, str]]] = {lg: [] for lg in ["en"] + L.NON_EN_LANGS}
    groups: dict[str, dict[str, str]] = {}
    new_state_pages: dict[str, str] = {}
    changed_urls: list[str] = []
    skipped = 0
    rendered = 0

    for (store, market, ch, genre), data in fetched:
        rows = data.get("rows", [])
        tkey = f"{store}:{market}:{ch}"
        fp = INC.fingerprint(rows)
        key = _content_key(store, ch, genre)
        hl_mapping = hreflang_by_key.get(key, {})
        for lang in _langs_for_market(market):
            url = page_url(lang, store, market, ch, genre)
            rel = page_rel_dir(lang, store, market, ch, genre).lstrip("/")
            dest_check = Path(out) / rel / "index.html"
            changed = INC.is_changed(prev_pages.get(url), fp, is_new_day) or not dest_check.exists()
            new_state_pages[url] = fp
            urls_by_lang[lang].append((url, date))
            if not changed:
                skipped += 1
                groups[url] = dict(hl_mapping)
                continue
            try:
                ins = compute_insights(rows, trend_cache[tkey], date, market, ch, lang=lang)
                dest, url, hl_map = render_page(lang, store, market, ch, date, genre,
                                                rows, trend_cache[tkey], ins, hl_mapping,
                                                lang_pages, out)
                groups[url] = hl_map
                changed_urls.append(url)
                rendered += 1
                print(f"[ok] [{lang}] {dest}")
            except Exception as e:
                print(f"[ERR] render [{lang}] {store}/{market}/{ch}/{genre}: {e}", file=sys.stderr)

    # ---- 各语言首页 ----
    home_pages = []
    for lang in ["en"] + L.NON_EN_LANGS:
        h = write_homepage(lang, urls_by_lang[lang], out, date)
        home_pages.append((home_url(lang), date))
        print(f"[ok] home [{lang}] {h}")

    all_urls = home_pages + [u for lang in ["en"] + L.NON_EN_LANGS for u in urls_by_lang[lang]]
    write_sitemap(all_urls, out)
    write_robots(out)
    write_not_found(out)
    INC.save_state(args.state, date, new_state_pages)

    errs = validate_hreflang(groups)
    if errs:
        print(f"[!] hreflang issues ({len(errs)}):", errs[:5], file=sys.stderr)

    print(f"\n[done] {len(all_urls)} URLs in sitemap; {rendered} pages rendered/updated; "
          f"{skipped} unchanged skipped → {out}/")

    if changed_urls and not args.no_indexnow:
        key_file = INC.write_key_file(out, C.INDEXNOW_KEY)
        if key_file:
            print(f"[i] IndexNow key file written: {key_file} (deploy it with the site)")
        res = INC.submit_indexnow(changed_urls, C.INDEXNOW_KEY)
        print(f"[indexnow] {res}")
    elif changed_urls:
        print(f"[indexnow] skipped by flag; {len(changed_urls)} URLs would be submitted.")


if __name__ == "__main__":
    main()
