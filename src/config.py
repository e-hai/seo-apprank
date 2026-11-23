# -*- coding: utf-8 -*-
"""
config.py — 应用榜单 SEO 站配置
数据源：e-hai/Appstore_Top_30 的静态 JSON API（GitHub Pages CDN）
设计原则：面向海外、免费、全自动、每页有真实数据与洞察。
"""
from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# 数据源
# ---------------------------------------------------------------------------
API_BASE = "https://e-hai.github.io/Appstore_Top_30/api"
REQUEST_TIMEOUT = 30  # seconds
UA = "AppRankSeoBot/1.0 (+https://apprank.pages.dev; data from App Store official feeds)"

# ---------------------------------------------------------------------------
# 榜单类型
# ---------------------------------------------------------------------------
CHARTS = {
    "free":     {"en": "Top Free",     "zh": "免费榜",   "ko": "무료 순위",      "ja": "無料ランキング", "tr": "Ücretsiz"},
    "paid":     {"en": "Top Paid",     "zh": "付费榜",   "ko": "유료 순위",      "ja": "有料ランキング", "tr": "Ücretli"},
    "grossing": {"en": "Top Grossing", "zh": "畅销榜",   "ko": "매출 순위",      "ja": "売上ランキング", "tr": "Hasılat"},
}
STORES = {
    "app_store": {"en": "App Store",     "zh": "App Store"},
    "play":      {"en": "Google Play",   "zh": "Google Play"},
}

# ---------------------------------------------------------------------------
# 市场（storefront）显示名 —— 多语言
# 注意：数据源按 39 个 storefront 分区。以下三个地区按中国表述规范显示；
# 全站统一用 "market / region" 而非 "country" 措辞。
# ---------------------------------------------------------------------------
CHINA_REGIONS = {"tw", "hk", "mo"}  # 需按中国表述规范处理的地区代码

MARKET_NAMES = {
    "us": ("United States", "美国"), "ca": ("Canada", "加拿大"),
    "mx": ("Mexico", "墨西哥"), "br": ("Brazil", "巴西"),
    "ar": ("Argentina", "阿根廷"), "cl": ("Chile", "智利"),
    "co": ("Colombia", "哥伦比亚"), "pe": ("Peru", "秘鲁"),
    "gb": ("United Kingdom", "英国"), "de": ("Germany", "德国"),
    "fr": ("France", "法国"), "it": ("Italy", "意大利"),
    "es": ("Spain", "西班牙"),
    "ae": ("United Arab Emirates", "阿联酋"), "sa": ("Saudi Arabia", "沙特阿拉伯"),
    "il": ("Israel", "以色列"), "tr": ("Türkiye", "土耳其"),
    "eg": ("Egypt", "埃及"), "ma": ("Morocco", "摩洛哥"),
    "jp": ("Japan", "日本"), "kr": ("South Korea", "韩国"),
    # 以下三个按中国表述规范
    "tw": ("Taiwan, China", "中国台湾"),
    "hk": ("Hong Kong, China", "中国香港"),
    "mo": ("Macao, China", "中国澳门"),
    "sg": ("Singapore", "新加坡"), "my": ("Malaysia", "马来西亚"),
    "th": ("Thailand", "泰国"), "id": ("Indonesia", "印度尼西亚"),
    "vn": ("Vietnam", "越南"), "ph": ("Philippines", "菲律宾"),
    "au": ("Australia", "澳大利亚"), "nz": ("New Zealand", "新西兰"),
    "in": ("India", "印度"), "pk": ("Pakistan", "巴基斯坦"),
    "bd": ("Bangladesh", "孟加拉国"), "lk": ("Sri Lanka", "斯里兰卡"),
    "za": ("South Africa", "南非"), "ng": ("Nigeria", "尼日利亚"),
    "ke": ("Kenya", "肯尼亚"),
}

# 各语言版本的本族市场名（仅覆盖该语言实际使用的市场，其余回退到英文名）
LOCAL_MARKET_NAMES = {
    "ko": {"kr": "한국"},
    "ja": {"jp": "日本"},
    "zh": {"tw": "中国台湾", "hk": "中国香港", "mo": "中国澳门"},
    "tr": {"tr": "Türkiye"},
}


def market_name(code: str, lang: str = "en") -> str:
    """返回市场显示名。英文用英文名，中文用规范中文名，其他语言优先本族市场名。"""
    if lang in LOCAL_MARKET_NAMES and code in LOCAL_MARKET_NAMES[lang]:
        return LOCAL_MARKET_NAMES[lang][code]
    pair = MARKET_NAMES.get(code, (code.upper(), code.upper()))
    return pair[0] if lang != "zh" else pair[1]

# ---------------------------------------------------------------------------
# hreflang 语言/地区码（ISO 639-1 + ISO 3166-1 Alpha-2）
# 中国三个地区用 zh-Hant-TW / zh-Hant-HK / zh-Hant-MO
# ---------------------------------------------------------------------------
def hreflang_code(market: str, lang: str = "en") -> str:
    """每个市场返回唯一 hreflang 码，避免多个市场共用 'en' 造成冲突。
    中国三个地区用繁体中文地区变体；其余按 en-XX 地区变体。"""
    base = {
        "tw": "zh-Hant-TW", "hk": "zh-Hant-HK", "mo": "zh-Hant-MO",
    }
    if market in base:
        return base[market]
    if lang != "en":
        return f"{lang}-{market.upper()}"
    return f"en-{market.upper()}"

# ---------------------------------------------------------------------------
# 品类显示名 —— 数据源字段是中文（"游戏"/"总榜"），英文页必须翻译后展示
# ---------------------------------------------------------------------------
GENRE_LABELS = {
    "游戏": "Games", "总榜": "Overall", "Games": "Games", "Overall": "Overall",
}

def genre_label(name: str, lang: str = "en") -> str:
    """把数据源的中文品类名转成页面显示名；未知值原样返回。"""
    if lang == "en":
        return GENRE_LABELS.get(name, name)
    if lang == "zh":
        return name  # 数据源就是中文
    # 数据源品类名的本地化（游戏 / 总榜）
    table = {
        "ko": {"游戏": "게임", "总榜": "전체", "GAME": "게임"},
        "ja": {"游戏": "ゲーム", "总榜": "総合", "GAME": "ゲーム"},
        "tr": {"游戏": "Oyunlar", "总榜": "Genel", "GAME": "Oyunlar"},
    }.get(lang, {})
    return table.get(name, name)

# ---------------------------------------------------------------------------
# 首批落地市场（P0 样本：先小后大，验证收录再扩量）
# 建议 5 个代表性市场：北美、西欧、东亚、东南亚、南亚
# ---------------------------------------------------------------------------
PILOT_MARKETS = ["us", "gb", "de", "jp", "sg"]

# 首批榜单（免费榜最通用）+ 品类（total + 游戏）
PILOT_CHART = "free"
PILOT_GENRES = [None, "6014"]  # None=总榜, 6014=iOS游戏总榜

# ---------------------------------------------------------------------------
# 全量策略（经实测 2026-11-20）
# 数据源实际有数据的组合：
#   - 总榜：2 平台 × 39 市场 × 3 榜 ≈ 231 个 URL（几乎全覆盖）
#   - 品类榜：仅游戏品类有数据（app_store=6014 覆盖 38 市场；play=GAME 需实测）
# 全量只生成"总榜 + 游戏榜"，不生成指向空数据的品类页（避免 thin content）。
# ---------------------------------------------------------------------------
ALL_STORES = ["app_store", "play"]
ALL_CHARTS = ["free", "paid", "grossing"]
ALL_MARKETS = list(MARKET_NAMES)
GENRE_BY_STORE = {
    "app_store": "6014",   # 游戏
    "play": "GAME",        # 游戏总榜（生成时验证存在性）
}

# IndexNow 设置（提交给参与协议的引擎，主要是 Bing / Yandex / Naver 等）
# 注意：Google 不在 IndexNow 参与列表，Google 收录仍靠 sitemap + GSC。
INDEXNOW_KEY = ""  # 上线前生成 32 位十六进制 key；并在站点根目录放置 {key}.txt
INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"

# 站点域名：默认 Cloudflare Pages 免费域名，可用环境变量 SITE_BASE_URL 覆盖。
# 换独立域名时，只需在 GitHub Actions 里设置变量 SITE_BASE_URL，无需改代码。
DEFAULT_BASE_URL = "https://apprank.pages.dev"
BASE_URL = os.environ.get("SITE_BASE_URL", DEFAULT_BASE_URL).rstrip("/")

SITE = {
    "name": "AppRank Index",
    "base_url": BASE_URL,
    "lang": "en",
}

# ---------------------------------------------------------------------------
# 每页"实质变化"判定阈值 —— 用于增量更新，避免伪更新
# ---------------------------------------------------------------------------
CHANGE_THRESHOLDS = {
    "rank_delta": 1,        # 名次变动 >=1
    "rating_delta": 0.1,    # 评分变动 >=0.1
    "rating_count_pct": 0.01,  # 评分数变动 >=1%
}
