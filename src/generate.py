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
    # 当 new 占比过高（如数据源首次抓取该榜），"N new entries" 会失真且无意义，
    # 改用稳健描述：只陈述榜单构成事实，不夸大"异动"。
    new_ratio = len(new_apps) / n if n else 0
    new_phrase = (
        (f"{len(new_apps)} of the listed apps are newly tracked" if lang == "en"
         else f"榜上 {len(new_apps)} 款为新增追踪")
        if new_ratio <= 0.5
        else ("several entries are being observed for the first time, so day-over-day "
              "movement is limited" if lang == "en" else "本次为该榜单的首次采样，日环比变动有限")
    )
    mover_phrase = (
        f"The biggest climber was {risers[0]['name']} (+{risers[0]['rank_change']} spots). "
        if risers else ("No apps gained positions in this snapshot. " if lang == "en"
                        else "本次采样中无应用名次上升。")
    )
    # 品类若全是"总榜"，不写"X 类别占比最高"这种无信息量的话
    # 数据源品类名为中文，英文页需翻译后展示
    top_genre_disp = C.genre_label(top_genre, lang)
    genre_phrase = (
        (f"{top_genre_disp} is the most represented category ({top_genre_n}/{n}). " if lang == "en"
         else f"{top_genre_disp} 类别占比最高（{top_genre_n}/{n}）。")
        if top_genre and top_genre_n < n else ""
    )
    if lang == "zh":
        insight = (
            f"截至 {date}，{mkt} {ch} Top {n} 中{new_phrase}；{mover_phrase}"
            f"{top_dev or '—'} 以 {top_dev_n} 款入榜成为上榜产品最多的开发者。"
            f"{genre_phrase}榜首为 {top.get('name', '—')}，评分 {top.get('rating', '—')}。"
        )
    else:
        insight = (
            f"As of {date}, {new_phrase} in the {mkt} {ch} Top {n}. {mover_phrase}"
            f"{top_dev or '—'} leads developers with {top_dev_n} apps on the board. "
            f"{genre_phrase}The current #1 is {top.get('name', '—')} with a "
            f"{top.get('rating', '—')} rating."
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
# hreflang 生成 + 校验
# ---------------------------------------------------------------------------
def hreflang_tags(sibling_urls: dict[str, str]) -> tuple[str, dict[str, str]]:
    """生成自引用 + 双向互指 + x-default 的 hreflang 标签组。
    sibling_urls: {market_code: full_url} —— 同一内容组（同 chart/品类）在各市场的 URL。
    只有实际生成的页面才进入互指集合，避免指向不存在页面。
    返回 (HTML 标签串, {lang_code: url} 映射) 供校验使用。"""
    mapping: dict[str, str] = {}
    for m, url in sibling_urls.items():
        mapping[C.hreflang_code(m, "en")] = url
    if "us" in sibling_urls:
        mapping["x-default"] = sibling_urls["us"]
    tags = "\n".join(
        f'    <link rel="alternate" hreflang="{html.escape(code)}" href="{html.escape(url)}"/>'
        for code, url in mapping.items()
    )
    return tags, mapping

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

# JS 逻辑独立成串，用 __ROWS_JSON__ 占位；注入后大括号不会被再次 format 解析。
APP_JS = r"""
const ROWS=__ROWS_JSON__;
let sortKey='rank',sortDir=1,activeFilter='all';
function esc(s){const d=document.createElement('div');d.textContent=(s==null?'':String(s));return d.innerHTML;}
function initial(s){return esc((s||'?').trim().charAt(0).toUpperCase());}
function rankHtml(n){
  const cls=n===1?'gold':n===2?'silver':n===3?'bronze':'';
  return '<span class="rk '+cls+'">'+n+'</span>';
}
function moveHtml(r){
  if(r.status==='new')return '<span class="move new">NEW</span>';
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
  ).join('')||'<tr class="empty-row"><td colspan="6">No apps match your filters.</td></tr>';
  document.getElementById('count').innerHTML='Showing <b>'+rs.length+'</b> of '+ROWS.length+' apps';
}
render();
"""

TPL = """<!doctype html>
<html lang="{lang}">
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
  <a class="brand" href="/"><span class="brand-ico">A</span><span>AppRank<span class="brand-dot">.</span>Index</span></a>
  <nav class="crumb"><a href="/">Home</a><span class="sep">/</span>{breadcrumb}</nav>
</div></header>

<main class="wrap">
  <section class="hero">
    <span class="hero-eyebrow">Daily chart \u00b7 {mkt} \u00b7 {ch}</span>
    <h1>{h1}</h1>
    <p class="hero-sub">A point-in-time snapshot of the top apps, with daily rank movement,
      historical position and insights computed from the real data.</p>
    <div class="meta-row">
      <span class="meta-pill"><span class="dot"></span>Last updated <b>{updated}</b></span>
      <span class="meta-pill"><span class="dot"></span>Source <b>{source_note}</b></span>
      {streak_note}
    </div>
  </section>

  <section class="insight-card">
    <div class="insight-icon">\u2726</div>
    <div><div class="insight-label">What changed today</div><p>{insight}</p></div>
  </section>

  <div class="stat-grid">{stats}</div>

  <section class="panel">
    <div class="panel-head">
      <div><h2>Top apps right now</h2><p class="panel-sub">Search, filter by movement, or click any column to sort.</p></div>
      <span class="result-count" id="count"></span>
    </div>
    <div class="toolbar">
      <label class="search"><span class="ico">\u26b2</span>
        <input id="q" type="search" placeholder="Filter by app or developer\u2026" oninput="render()"/></label>
      <div class="segments">
        <button class="seg active" data-f="all" onclick="setFilter('all',this)">All</button>
        <button class="seg" data-f="up" onclick="setFilter('up',this)">Climbers</button>
        <button class="seg" data-f="down" onclick="setFilter('down',this)">Falling</button>
        <button class="seg" data-f="new" onclick="setFilter('new',this)">New</button>
      </div>
    </div>
    <div class="table-scroll">
      <table class="rank"><thead><tr>
        <th data-k="rank" onclick="sortBy('rank')">#<span class="arrow"></span></th>
        <th data-k="name" onclick="sortBy('name')">App<span class="arrow"></span></th>
        <th data-k="developer" onclick="sortBy('developer')">Developer<span class="arrow"></span></th>
        <th data-k="category" onclick="sortBy('category')">Category<span class="arrow"></span></th>
        <th data-k="rating" onclick="sortBy('rating')">Rating<span class="arrow"></span></th>
        <th data-k="change" onclick="sortBy('change')">Move<span class="arrow"></span></th>
      </tr></thead><tbody id="tb"></tbody></table>
    </div>
  </section>

  <section class="panel">
    <h2>Rank history <span class="muted-sm">top 5 \u00b7 best position by day</span></h2>
    <div class="spark-grid">{spark}</div>
  </section>

  <div class="two-col">
    <section class="panel prose"><h2>Methodology</h2><p>{methodology}</p></section>
    <section class="panel"><h2>Good to know</h2>{faq}</section>
  </div>
</main>

<footer><div class="wrap">
  <div class="footer-brand">AppRank<span class="brand-dot">.</span>Index</div>
  <p>{attribution}</p>
  <p>Last updated {updated}. Rankings are a point-in-time sample and may differ from real-time store placement.</p>
</div></footer>
<script>{app_js}</script>
</body>
</html>
"""

def render_page(store, market, chart, date, genre, rows, trend, insights, sibling_urls, out_root):
    lang = C.SITE["lang"]
    mkt = C.market_name(market, lang)
    ch = C.CHARTS[chart][lang]
    gn = C.genre_label("游戏", lang) if genre else None  # 品类页当前仅"游戏"，显示可读标签
    h1 = f"{ch} Apps in {mkt} — {date}" + (f" ({gn})" if gn else "")
    title = f"{ch} Apps in {mkt} ({date}) | {C.SITE['name']}"
    description = make_description(insights["insight"])

    # URL 结构：/{store}/{market}/top/{chart}/（区分双平台，避免撞车；品类页加 /{genre}/）
    parts = [store, market, "top", chart] + ([genre] if genre else [])
    rel_dir = "/".join(parts)
    url = f"{C.SITE['base_url']}/{rel_dir}/"
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    source_note = "App Store official charts"
    if store == "play":
        source_note = "Google Play official charts"
    methodology = (
        f"This page ranks the top apps on the {ch} chart in {mkt} for {date}. "
        f"Data is pulled from a daily snapshot of official storefront charts, sampled once per day. "
        f"Rank movement compares against the previous available day. "
        f"Ratings and developer names are shown as provided by the source. "
        f"This is a point-in-time sample, not a real-time feed."
    )
    streak_note = (
        f'<span class="meta-pill"><span class="dot"></span>Longest streak <b>'
        f'{insights["longest_streak"]} days</b></span>'
        if insights['longest_streak'] else ""
    )

    # 统计卡片：由当日真实数据计算
    top = rows[0] if rows else {}
    risers = insights.get("risers") or []
    biggest = risers[0] if risers else None
    def stat(k, v, s="", accent=False):
        vc = " accent" if accent else ""
        return (f'<div class="stat"><div class="stat-k">{html.escape(k)}</div>'
                f'<div class="stat-v{vc}" title="{html.escape(str(v))}">{html.escape(str(v))}</div>'
                + (f'<div class="stat-s">{html.escape(str(s))}</div>' if s else "") + '</div>')
    stats = "".join([
        stat("#1 right now", top.get("name", "\u2014"),
             f'{ch} in {mkt}', accent=True),
        stat("New this snapshot", str(insights["new_count"]), "apps entering the board"),
        stat("Biggest climber", biggest["name"] if biggest else "\u2014",
             (f'+{biggest["rank_change"]} spots' if biggest else "no movement")),
        stat("Top developer", insights["top_dev"] or "\u2014",
             f'{insights["top_dev_n"]} apps on the board'),
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
                f'<p class="spark-meta">Best rank over {len(recent)} observed days</p>'
                f'{trend_svg(recent, uid=f"c{i}")}</div>'
            )
    spark = ("\n".join(spark_parts) or
             "<p class='muted-sm'>Trend data not yet available for this market.</p>")

    faq = (
        "<details><summary>How often is this data updated?</summary>"
        "<p>The source dataset publishes a new snapshot daily. This page shows the latest available date shown above.</p></details>"
        "<details><summary>Is this the official App Store ranking?</summary>"
        "<p>Rankings are sourced from official storefront charts via a third-party open dataset and represent a daily sample, not the live store. For real-time placement, check the official store.</p></details>"
        "<details><summary>Do you own this data?</summary>"
        "<p>No. App names, icons and ratings belong to their respective owners. This page presents factual ranking data with attribution and links to the official stores.</p></details>"
    )

    attribution = (
        "Data source: <a href='https://github.com/e-hai/Appstore_Top_30' rel='nofollow'>e-hai/Appstore_Top_30</a> "
        "(daily snapshots of Apple App Store / Google Play official charts). "
        "App Store is a trademark of Apple Inc. Google Play is a trademark of Google LLC. "
        "All app names and marks belong to their respective owners."
    )

    hl, hl_map = hreflang_tags(sibling_urls)
    jsonld = json.dumps([dataset_schema(rows, date, market, chart, lang)] + software_schema(rows),
                        ensure_ascii=False)

    # 给 JS 的精简行数据
    js_rows = [{
        "curr_rank": r.get("curr_rank"), "name": r.get("name", ""),
        "developer": r.get("developer", ""),
        "genre_name": C.genre_label(r.get("genre_name", ""), lang),
        "rating": r.get("rating"), "rank_change": r.get("rank_change") or 0,
        "status": r.get("status", ""),
    } for r in rows]

    app_js = APP_JS.replace("__ROWS_JSON__", json.dumps(js_rows, ensure_ascii=False))
    page = TPL.format(
        lang=lang, title=html.escape(title), description=html.escape(description),
        canonical=url, hreflang=hl, jsonld=jsonld, style=STYLE, app_js=app_js,
        breadcrumb=f"{mkt} / {ch}", h1=html.escape(h1), mkt=html.escape(mkt), ch=html.escape(ch),
        updated=updated, source_note=source_note, streak_note=streak_note,
        insight=html.escape(insights["insight"]), methodology=html.escape(methodology),
        stats=stats, spark=spark, faq=faq, attribution=attribution,
    )
    dest = Path(out_root) / rel_dir / "index.html"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(page, encoding="utf-8")
    return str(dest), url, hl_map

# ---------------------------------------------------------------------------
# Sitemap
# ---------------------------------------------------------------------------
def write_homepage(urls: list[tuple[str, str]], out_root: str, date: str):
    """生成根首页 /index.html：作为全站导航枢纽，链接到所有已生成的榜单页。
    只输出实际存在的页面链接（urls 来自本轮 fetch 结果），避免死链。"""
    base = C.SITE["base_url"].rstrip("/")
    existing = {u.rstrip("/") for u, _ in urls}

    def cell(store, m, ch, g=None):
        parts = [store, m, "top", ch] + ([g] if g else [])
        url = f"{base}/{'/'.join(parts)}/"
        if url.rstrip("/") not in existing:
            return '<span class="dash">\u2014</span>'
        label = C.CHARTS[ch]["en"] + (f" \u00b7 {C.genre_label('游戏', 'en')}" if g else "")
        return f'<a class="chart-link" href="{html.escape(url)}">{html.escape(label)}</a>'

    n = len(existing)
    desc = (f"Daily Top 30 app charts for {len(C.ALL_MARKETS)} markets across the App Store and "
            f"Google Play: free, paid, grossing and games, with rank history and insights. "
            f"Snapshot {date}.")

    store_panels = []
    for s in C.ALL_STORES:
        platform_table_rows = []
        genre = C.GENRE_BY_STORE.get(s)
        head = ("<tr><th>Market</th><th>Top Free</th><th>Top Paid</th><th>Top Grossing</th>"
                "<th>Games \u00b7 Free</th><th>Games \u00b7 Paid</th><th>Games \u00b7 Grossing</th></tr>")
        for m in C.ALL_MARKETS:
            cells = [f'<td class="mkt">{html.escape(C.market_name(m, "en"))}</td>']
            cells += [f"<td>{cell(s, m, ch)}</td>" for ch in C.ALL_CHARTS]
            cells += [f"<td>{cell(s, m, ch, genre) if genre else '—'}</td>" for ch in C.ALL_CHARTS]
            platform_table_rows.append("<tr>" + "".join(cells) + "</tr>")
        store_panels.append(
            f'<section class="panel"><div class="panel-head"><div>'
            f'<h2>{html.escape(C.STORES[s]["en"])}</h2>'
            f'<p class="panel-sub">Browse live chart pages by market and ranking type.</p>'
            f'</div></div><div class="table-scroll"><table class="matrix">{head}'
            f'{"".join(platform_table_rows)}</table></div></section>')

    stat_grid = "".join([
        f'<div class="stat"><div class="stat-k">Markets</div>'
        f'<div class="stat-v accent">{len(C.ALL_MARKETS)}</div>'
        f'<div class="stat-s">storefronts worldwide</div></div>',
        f'<div class="stat"><div class="stat-k">Chart pages</div>'
        f'<div class="stat-v">{n}</div><div class="stat-s">indexed &amp; updated daily</div></div>',
        f'<div class="stat"><div class="stat-k">Platforms</div>'
        f'<div class="stat-v">2</div><div class="stat-s">App Store &amp; Google Play</div></div>',
        f'<div class="stat"><div class="stat-k">Last snapshot</div>'
        f'<div class="stat-v" style="font-size:1.05rem">{html.escape(date)}</div>'
        f'<div class="stat-s">fresh data every day</div></div>',
    ])
    store_panels_html = "\n".join(store_panels)
    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{html.escape(C.SITE['name'])} \u2014 Daily App Store &amp; Google Play Top 30 Charts</title>
<meta name="description" content="{html.escape(desc)}"/>
<meta name="robots" content="index,follow"/>
<link rel="canonical" href="{html.escape(base)}/"/>
<link rel="alternate" hreflang="x-default" href="{html.escape(base)}/"/>
<script type="application/ld+json">{{
  "@context":"https://schema.org","@type":"Dataset",
  "name":"{html.escape(C.SITE['name'])} \u2014 Daily App Charts",
  "description":"{html.escape(desc)}",
  "creator":{{"@type":"Organization","name":"{html.escape(C.SITE['name'])}"}},
  "temporalCoverage":"{date}","isAccessibleForFree":true,
  "sameAs":"https://e-hai.github.io/Appstore_Top_30/api/"
}}</script>
<style>{STYLE}</style>
</head>
<body>
<header class="topbar"><div class="wrap">
  <a class="brand" href="/"><span class="brand-ico">A</span><span>AppRank<span class="brand-dot">.</span>Index</span></a>
  <nav class="crumb"><span class="meta-pill" style="border-color:#334155;background:#1e293b;color:#cbd5e1">\u00b7 Daily app chart directory</span></nav>
</div></header>

<main class="wrap">
  <section class="hero">
    <span class="hero-eyebrow">Free \u00b7 Paid \u00b7 Grossing \u00b7 Games</span>
    <h1>App charts, tracked daily.</h1>
    <p class="hero-sub">Daily snapshots of the top apps in {len(C.ALL_MARKETS)} markets on the App Store
      and Google Play. Every page shows the current board, rank movement, a rank-history chart
      and a short insight computed from that day's real data.</p>
    <div class="meta-row">
      <span class="meta-pill"><span class="dot"></span>Updated daily</span>
      <span class="meta-pill"><span class="dot"></span>Source: <b>e-hai/Appstore_Top_30</b></span>
    </div>
  </section>

  <div class="stat-grid">{stat_grid}</div>

  {store_panels_html}
</main>

<footer><div class="wrap">
  <div class="footer-brand">AppRank<span class="brand-dot">.</span>Index</div>
  <p>Data source: <a href="https://github.com/e-hai/Appstore_Top_30" rel="nofollow">e-hai/Appstore_Top_30</a>
    \u2014 daily snapshots of Apple App Store / Google Play official charts, not a live feed.</p>
  <p>App Store is a trademark of Apple Inc. Google Play is a trademark of Google LLC.
    All app names and marks belong to their respective owners.</p>
</div></footer>
</body>
</html>"""
    Path(out_root, "index.html").write_text(page, encoding="utf-8")

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

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def build_jobs(mode: str):
    """返回 jobs: [(store, market, chart, genre)]"""
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
    print(f"[i] jobs to process: {len(jobs)}")

    # 分 store+chart+genre 组构建 sibling URL（hreflang 互指）
    def page_url(store: str, m: str, ch: str, g: str | None) -> str:
        parts = [store, m, "top", ch] + ([g] if g else [])
        return f"{C.SITE['base_url']}/{'/'.join(parts)}/"

    groups_by_key: dict[tuple, dict[str, str]] = {}
    markets_all = C.ALL_MARKETS
    for store in C.ALL_STORES:
        for ch in C.ALL_CHARTS:
            for g in [None] + ([C.GENRE_BY_STORE[store]] if store in C.GENRE_BY_STORE else []):
                groups_by_key[(store, ch, g or "total")] = {
                    m: page_url(store, m, ch, g) for m in markets_all
                }

    # 增量状态
    state = INC.load_state(args.state)
    prev_pages: dict[str, str] = state.get("pages", {})
    is_new_day = state.get("date") != date
    print(f"[i] state date={state.get('date')}  is_new_day={is_new_day}")

    # ---- 并发拉取所有 ranking（网络等待从 N×延迟 降到 ~N/workers 批）----
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

    # ---- 并发拉取所需 trend（按 store:market:ch 去重）----
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

    # ---- 串行渲染（本地 IO，快）----
    urls, groups = [], {}
    new_state_pages: dict[str, str] = {}
    changed_urls: list[str] = []
    skipped = 0

    for (store, market, ch, genre), data in fetched:
        try:
            rows = data.get("rows", [])
            tkey = f"{store}:{market}:{ch}"
            url = page_url(store, market, ch, genre)
            fp = INC.fingerprint(rows)
            dest_check = Path(out) / "/".join(
                [store, market, "top", ch] + ([genre] if genre else [])) / "index.html"
            changed = INC.is_changed(prev_pages.get(url), fp, is_new_day) or not dest_check.exists()
            if not changed:
                skipped += 1
                new_state_pages[url] = fp
                urls.append((url, date))
                key = (store, ch, genre or "total")
                groups[url] = _map_to_codes(groups_by_key.get(key, {}))
                continue

            ins = compute_insights(rows, trend_cache[tkey], date, market, ch, lang="en")
            sibling_urls = groups_by_key[(store, ch, genre or "total")]
            dest, url, hl_map = render_page(store, market, ch, date, genre,
                                            rows, trend_cache[tkey], ins, sibling_urls, out)
            groups[url] = hl_map
            urls.append((url, date))
            new_state_pages[url] = fp
            changed_urls.append(url)
            print(f"[ok] {dest}")
        except Exception as e:
            print(f"[ERR] render {store}/{market}/{ch}/{genre}: {e}", file=sys.stderr)

    write_homepage(urls, out, date)          # 根首页 /index.html（导航枢纽）
    # sitemap 纳入首页
    home_url = f"{C.SITE['base_url'].rstrip('/')}/"
    write_sitemap([(home_url, date)] + urls, out)
    write_robots(out)
    INC.save_state(args.state, date, new_state_pages)

    errs = validate_hreflang(groups)
    if errs:
        print(f"[!] hreflang issues ({len(errs)}):", errs[:5], file=sys.stderr)

    print(f"\n[done] {len(urls)} pages in sitemap; {len(changed_urls)} changed/created; "
          f"{skipped} unchanged skipped → {out}/")

    # IndexNow 提交（仅变化 URL）
    if changed_urls and not args.no_indexnow:
        key_file = INC.write_key_file(out, C.INDEXNOW_KEY)
        if key_file:
            print(f"[i] IndexNow key file written: {key_file} (deploy it with the site)")
        res = INC.submit_indexnow(changed_urls, C.INDEXNOW_KEY)
        print(f"[indexnow] {res}")
    elif changed_urls:
        print(f"[indexnow] skipped by flag; {len(changed_urls)} URLs would be submitted.")


def _map_to_codes(sibling_urls: dict[str, str]) -> dict[str, str]:
    """从 {market: url} 反推 {hreflang_code: url}，用于未重渲染页的校验记录。"""
    mapping = {}
    for m, url in sibling_urls.items():
        mapping[C.hreflang_code(m, "en")] = url
    if "us" in sibling_urls:
        mapping["x-default"] = sibling_urls["us"]
    return mapping

if __name__ == "__main__":
    main()
