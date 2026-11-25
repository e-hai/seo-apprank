# -*- coding: utf-8 -*-
"""
locales.py — 应用榜单站多语言文案层

设计原则：
1. 每种语言聚焦自己的母语市场（ko→kr, ja→jp, zh→tw/hk/mo, tr→tr），
   而不是把全部 39 个市场的页面逐页翻译。这样每个语言版本都有真实的
   本地市场数据，避免"批量翻译低价值页面"的规模化内容风险。
2. 英文为默认语言，URL 不加前缀；其他语言加 /{lang}/ 前缀。
3. 所有洞察模板由当日真实数据填充，不是模板套话。
4. hreflang 使用 language-region 变体码，x-default 指向英文页。
"""
from __future__ import annotations

# 非英文语言与其覆盖的市场。英文覆盖全部市场，由 generate 用 C.ALL_MARKETS 处理。
LANG_MARKETS = {
    "ko": ["kr"],
    "ja": ["jp"],
    "zh": ["tw", "hk", "mo"],
    "tr": ["tr"],
}
NON_EN_LANGS = list(LANG_MARKETS)


def hreflang_code(lang: str, market: str) -> str:
    """语言版本的 hreflang 码。英文沿用 config 的市场码；非英文用 language-region。"""
    if lang == "en":
        return None  # 由 config.hreflang_code(market, 'en') 决定
    if lang == "zh":
        return f"zh-Hans-{market.upper()}"
    return f"{lang}-{market.upper()}"


LOCALES = {
    "en": {
        "h1_chart": "{ch} Apps in {mkt} — {date}", "title_chart": "{ch} Apps in {mkt} ({date}) | {site}",
        "label": "English", "native": "English", "html_lang": "en",
        "brand_tag": "· Daily app chart directory",
        "nav_home": "Home", "lang_label": "Language",
        "lang_partial_hint": "This language covers only its own market pages",
        "hero_eyebrow_chart": "Daily chart",
        "hero_sub_chart": ("A point-in-time snapshot of the top apps, with daily rank movement, "
                           "historical position and insights computed from the real data."),
        "meta_last_updated": "Last updated", "meta_source": "Source",
        "meta_longest_streak": "Longest streak", "days": "days",
        "insight_label": "What changed today",
        "stat_1": "#1 right now", "stat_2": "New this snapshot",
        "stat_3": "Biggest climber", "stat_4": "Top developer",
        "stat_2_sub": "apps entering the board", "stat_3_none": "no movement",
        "stat_spots": "spots", "stat_apps_board": "apps on the board",
        "tbl_title": "Top apps right now",
        "tbl_sub": "Search, filter by movement, or click any column to sort.",
        "search_ph": "Filter by app or developer…",
        "seg_all": "All", "seg_up": "Climbers", "seg_down": "Falling", "seg_new": "New",
        "th_rank": "#", "th_app": "App", "th_developer": "Developer",
        "th_category": "Category", "th_rating": "Rating", "th_move": "Move",
        "count_fmt": "Showing <b>{a}</b> of {b} apps",
        "empty": "No apps match your filters.",
        "rank_title": "Rank history", "rank_sub": "top 5 · best position by day",
        "best_over": "Best rank over {n} observed days",
        "method_title": "Methodology", "faq_title": "Good to know",
        "footer_source_prefix": "Data source:",
        "footer_tm": ("App Store is a trademark of Apple Inc. Google Play is a trademark of Google LLC. "
                      "All app names and marks belong to their respective owners."),
        "footer_note": ("Last updated {updated}. Rankings are a point-in-time sample and may differ "
                        "from real-time store placement."),
        "home_eyebrow": "Free · Paid · Grossing · Games",
        "home_title": "App charts, tracked daily.",
        "home_sub": ("Daily snapshots of the top apps in {n} markets on the App Store and Google Play. "
                     "Every page shows the current board, rank movement, a rank-history chart "
                     "and a short insight computed from that day's real data."),
        "home_updated": "Updated daily", "home_source_label": "Source: ",
        "stat_markets": "Markets", "stat_markets_sub": "storefronts worldwide",
        "stat_pages": "Chart pages", "stat_pages_sub": "indexed & updated daily",
        "stat_platforms": "Platforms", "stat_platforms_sub": "App Store & Google Play",
        "stat_snapshot": "Last snapshot", "stat_snapshot_sub": "fresh data every day",
        "browse_sub": "Browse live chart pages by market and ranking type.",
        "mx_market": "Market", "mx_free": "Top Free", "mx_paid": "Top Paid",
        "mx_grossing": "Top Grossing", "mx_gfree": "Games · Free",
        "mx_gpaid": "Games · Paid", "mx_ggrossing": "Games · Grossing",
        "methodology": ("This page ranks the top apps on the {ch} chart in {mkt} for {date}. "
                        "Data is pulled from a daily snapshot of official storefront charts, "
                        "sampled once per day. Rank movement compares against the previous "
                        "available day. Ratings and developer names are shown as provided by "
                        "the source. This is a point-in-time sample, not a real-time feed."),
        "faq": [
            ("How often is this data updated?",
             "The source dataset publishes a new snapshot daily. This page shows the latest available date shown above."),
            ("Is this the official App Store ranking?",
             "Rankings are sourced from official storefront charts via a third-party open dataset and represent a daily sample, not the live store. For real-time placement, check the official store."),
            ("Do you own this data?",
             "No. App names, icons and ratings belong to their respective owners. This page presents factual ranking data with attribution and links to the official stores."),
        ],
        "insight": {
            "frame": "As of {date}, {new} in the {mkt} {ch} Top {n}. {mover}{dev}{genre}{top}",
            "new_low": "{n} of the listed apps are newly tracked",
            "new_high": ("several entries are being observed for the first time, so day-over-day "
                         "movement is limited"),
            "mover": "The biggest climber was {name} (+{n} spots). ",
            "mover_none": "No apps gained positions in this snapshot. ",
            "dev": "{dev} leads developers with {n} apps on the board. ",
            "genre": "{genre} is the most represented category ({n}/{total}). ",
            "top": "The current #1 is {name} with a {rating} rating.",
        },
    },

    "ko": {
        "h1_chart": "{mkt} {ch} — {date}", "title_chart": "{mkt} {ch} ({date}) | {site}",
        "label": "Korean", "native": "한국어", "html_lang": "ko",
        "brand_tag": "· 매일 앱 차트 디렉터리",
        "nav_home": "홈", "lang_label": "언어",
        "lang_partial_hint": "이 언어는 자국 시장 페이지만 제공합니다",
        "hero_eyebrow_chart": "매일 차트",
        "hero_sub_chart": ("주요 앱의 현재 순위와 일별 변동, 과거 순위, 그리고 실제 데이터로 "
                           "계산한 인사이트를 한눈에 보여드립니다."),
        "meta_last_updated": "최종 업데이트", "meta_source": "출처",
        "meta_longest_streak": "최장 연속 순위", "days": "일",
        "insight_label": "오늘의 변화",
        "stat_1": "현재 1위", "stat_2": "이번 스냅샷 신규",
        "stat_3": "최대 상승", "stat_4": "최다 출품 개발사",
        "stat_2_sub": "신규 진입 앱", "stat_3_none": "변동 없음",
        "stat_spots": "계단", "stat_apps_board": "개 앱 진입",
        "tbl_title": "현재 상위 앱",
        "tbl_sub": "검색하고 변동으로 필터링하거나 열을 눌러 정렬할 수 있습니다.",
        "search_ph": "앱 또는 개발사 검색…",
        "seg_all": "전체", "seg_up": "상승", "seg_down": "하락", "seg_new": "신규",
        "th_rank": "#", "th_app": "앱", "th_developer": "개발사",
        "th_category": "카테고리", "th_rating": "평점", "th_move": "변동",
        "count_fmt": "총 {b}개 중 <b>{a}</b>개 표시",
        "empty": "검색 조건에 맞는 앱이 없습니다.",
        "rank_title": "순위 추이", "rank_sub": "상위 5개 · 일별 최고 순위",
        "best_over": "{n}일간 관찰된 최고 순위",
        "method_title": "방법론", "faq_title": "알아두세요",
        "footer_source_prefix": "데이터 출처:",
        "footer_tm": ("App Store는 Apple Inc.의 상표이고 Google Play는 Google LLC의 상표입니다. "
                      "모든 앱 이름과 로고는 각 소유자에게 소유됩니다."),
        "footer_note": ("최종 업데이트 {updated}. 순위는 특정 시점의 표본으로, 실시간 스토어 순위와 "
                        "다를 수 있습니다."),
        "home_eyebrow": "무료 · 유료 · 매출 · 게임",
        "home_title": "앱 차트를 매일 기록합니다.",
        "home_sub": ("App Store와 Google Play의 {n}개 시장에서 매일 수집한 주요 앱의 스냅샷입니다. "
                     "모든 페이지에서 현재 순위, 순위 변동, 순위 추이 차트와 당일 실제 데이터로 "
                     "계산한 간단한 인사이트를 보여드립니다."),
        "home_updated": "매일 업데이트", "home_source_label": "출처: ",
        "stat_markets": "시장", "stat_markets_sub": "전 세계 스토어프런트",
        "stat_pages": "차트 페이지", "stat_pages_sub": "매일 업데이트 내 인덱스",
        "stat_platforms": "플랫폼", "stat_platforms_sub": "App Store & Google Play",
        "stat_snapshot": "최신 스냅샷", "stat_snapshot_sub": "매일 새로운 데이터",
        "browse_sub": "시장과 순위 유형별로 차트 페이지를 탐색하세요.",
        "mx_market": "시장", "mx_free": "무료 순위", "mx_paid": "유료 순위",
        "mx_grossing": "매출 순위", "mx_gfree": "게임 · 무료",
        "mx_gpaid": "게임 · 유료", "mx_ggrossing": "게임 · 매출",
        "methodology": ("이 페이지는 {date} 기준 {mkt} {ch} 차트의 주요 앱을 순위별로 보여줍니다. "
                        "데이터는 공식 스토어 차트의 매일 스냅샷에서 가져오며 하루 한 번씩 수집합니다. "
                        "순위 변동은 이전 측정일과 비교합니다. 평점과 개발사 이름은 데이터 출처에서 "
                        "제공한 대로 표시합니다. 이는 특정 시점의 표본이며 실시간 피드가 아닙니다."),
        "faq": [
            ("데이터는 얼마나 자주 업데이트되나요?",
             "출처 데이터셋은 매일 새로운 스냅샷을 공개합니다. 이 페이지는 위에 표시된 가장 최신 날짜를 보여줍니다."),
            ("이것이 공식 App Store 순위인가요?",
             "순위는 제3자 공개 데이터셋을 통해 공식 스토어 차트에서 가져온 일별 표본이며 실시간 스토어가 아닙니다. 실시간 순위는 공식 스토어에서 확인하세요."),
            ("이 데이터의 소유권이 있나요?",
             "아니요. 앱 이름, 아이콘, 평점은 각 소유자에게 있습니다. 이 페이지는 출처를 명시하고 공식 스토어 링크와 함께 사실적인 순위 데이터를 제시합니다."),
        ],
        "insight": {
            "frame": "{date} 기준 {mkt} {ch} Top {n}에서 {new}{mover}{dev}{genre}{top}",
            "new_low": "목록에 오른 앱 {n}개가 신규로 추적되었습니다",
            "new_high": "처음 추적되는 항목이 있어 일별 변동은 제한적입니다",
            "mover": "최대 상승은 {name}(+{n} 계단)입니다. ",
            "mover_none": "이 스냅샷에서 순위가 상승한 앱은 없었습니다. ",
            "dev": "{dev}이 {n}개를 진입시켜 개발사 순위 1위입니다. ",
            "genre": "{genre} 카테고리가 {n}/{total}로 가장 많습니다. ",
            "top": "현재 1위는 {name}이고 평점은 {rating}입니다.",
        },
    },

    "ja": {
        "h1_chart": "{mkt}の{ch} — {date}", "title_chart": "{mkt}の{ch} ({date}) | {site}",
        "label": "Japanese", "native": "日本語", "html_lang": "ja",
        "brand_tag": "· 毎日アプリランキングディレクトリ",
        "nav_home": "ホーム", "lang_label": "言語",
        "lang_partial_hint": "この言語は自国市場のページのみ提供しています",
        "hero_eyebrow_chart": "毎日ランキング",
        "hero_sub_chart": ("主要アプリの現在の順位と日次の変動、過去の順位、そして実際のデータから"
                           "計算したインサイトを一目で示します。"),
        "meta_last_updated": "最終更新", "meta_source": "出典",
        "meta_longest_streak": "最長連続順位", "days": "日",
        "insight_label": "本日の変化",
        "stat_1": "現在 1 位", "stat_2": "今回のスナップショットで新規",
        "stat_3": "最大上昇", "stat_4": "最多選出開発元",
        "stat_2_sub": "新規エントリー", "stat_3_none": "変動なし",
        "stat_spots": "位", "stat_apps_board": "件のアプリ",
        "tbl_title": "現在の主要アプリ",
        "tbl_sub": "検索、変動でのフィルタリング、列クリックでの並び替えができます。",
        "search_ph": "アプリまたは開発元で検索…",
        "seg_all": "すべて", "seg_up": "上昇", "seg_down": "下落", "seg_new": "新規",
        "th_rank": "#", "th_app": "アプリ", "th_developer": "開発元",
        "th_category": "カテゴリー", "th_rating": "評価", "th_move": "変動",
        "count_fmt": "{b} 件中 <b>{a}</b> 件を表示",
        "empty": "条件に一致するアプリがありません。",
        "rank_title": "順位推移", "rank_sub": "上位 5 件 · 日別の最高順位",
        "best_over": "{n}日間の観測で最高順位",
        "method_title": "方法論", "faq_title": "ご存知の点",
        "footer_source_prefix": "データ出典:",
        "footer_tm": ("App Store は Apple Inc. の商標で、Google Play は Google LLC の商標です。"
                      "アプリ名およびロゴは各所有者に属します。"),
        "footer_note": ("最終更新 {updated}。順位はある時点のサンプルであり、リアルタイムの"
                        "ストア順位とは異なる場合があります。"),
        "home_eyebrow": "無料 · 有料 · 売上 · ゲーム",
        "home_title": "アプリランキングを毎日記録します。",
        "home_sub": ("App Store と Google Play の {n} 市場の主要アプリを毎日スナップショット"
                     "しています。各ページで現在の順位、順位変動、順位推移チャート、そしてその日の"
                     "実際のデータから計算した短いインサイトを示します。"),
        "home_updated": "毎日更新", "home_source_label": "出典: ",
        "stat_markets": "市場", "stat_markets_sub": "世界中のストア",
        "stat_pages": "ランキングページ", "stat_pages_sub": "毎日更新・インデックス済み",
        "stat_platforms": "プラットフォーム", "stat_platforms_sub": "App Store & Google Play",
        "stat_snapshot": "最新スナップショット", "stat_snapshot_sub": "毎日の新しいデータ",
        "browse_sub": "市場とランキング種類別にページをご覧ください。",
        "mx_market": "市場", "mx_free": "無料ランキング", "mx_paid": "有料ランキング",
        "mx_grossing": "売上ランキング", "mx_gfree": "ゲーム · 無料",
        "mx_gpaid": "ゲーム · 有料", "mx_ggrossing": "ゲーム · 売上",
        "methodology": ("このページは {date} 時点の {mkt} {ch} チャートの主要アプリを順位付け"
                        "しています。データは公式ストアチャートの日次スナップショットから取得し、"
                        "一日一度サンプリングしています。順位変動は直前の計測日と比較します。"
                        "評価と開発元名は出典のまま示しています。これはある時点のサンプルであり、"
                        "リアルタイムのフィードではありません。"),
        "faq": [
            ("このデータはどのくらいの頻度で更新されますか？",
             "出典データセットは毎日新しいスナップショットを公開します。このページは上記の最新日付を示しています。"),
            ("これは公式の App Store 順位ですか？",
             "順位は第三者の公開データセットを通じて公式ストアチャートから得た日次サンプルで、リアルタイムのストアではありません。リアルタイム順位は公式ストアでご確認ください。"),
            ("このデータの著作権はありますか？",
             "ありません。アプリ名、アイコン、評価は各所有者に属します。このページは出典を明記し、公式ストアへのリンクと共に事実の順位データを示します。"),
        ],
        "insight": {
            "frame": "{date} 時点の {mkt} {ch} Top {n} では {new}{mover}{dev}{genre}{top}",
            "new_low": "掲載アプリのうち {n} 件が新規追跡となりました",
            "new_high": "初めて掲載される項目があり、日次変動は限定的です",
            "mover": "最大の上昇は {name}（+{n} 位）です。 ",
            "mover_none": "このスナップショットで順位を上げたアプリはありませんでした。 ",
            "dev": "{dev} が {n} 件で最多選出の開発元です。 ",
            "genre": "{genre} カテゴリーが {n}/{total} と最も多い割合です。 ",
            "top": "現在の 1 位は {name}、評価は {rating} です。",
        },
    },

    "zh": {
        "h1_chart": "{mkt}{ch} — {date}", "title_chart": "{mkt}{ch}（{date}）| {site}",
        "label": "Chinese", "native": "中文", "html_lang": "zh-CN",
        "brand_tag": "· 每日应用榜单目录",
        "nav_home": "首页", "lang_label": "语言",
        "lang_partial_hint": "该语言仅提供本地市场页面",
        "hero_eyebrow_chart": "每日榜单",
        "hero_sub_chart": ("一目了然地查看主要应用的当前排名、日环比变动、历史位置，以及根据真实"
                           "数据计算的洞察。"),
        "meta_last_updated": "最后更新", "meta_source": "数据来源",
        "meta_longest_streak": "最长连续在榜", "days": "天",
        "insight_label": "今日变化",
        "stat_1": "当前第一", "stat_2": "本次新增",
        "stat_3": "最大涨幅", "stat_4": "上榜最多开发者",
        "stat_2_sub": "新进入榜的应用", "stat_3_none": "无变动",
        "stat_spots": "位", "stat_apps_board": "款应用入榜",
        "tbl_title": "当前主要应用",
        "tbl_sub": "可搜索、按变动筛选，或点击列头排序。",
        "search_ph": "按应用或开发者筛选…",
        "seg_all": "全部", "seg_up": "上涨", "seg_down": "下跌", "seg_new": "新增",
        "th_rank": "#", "th_app": "应用", "th_developer": "开发者",
        "th_category": "类别", "th_rating": "评分", "th_move": "变动",
        "count_fmt": "共 {b} 个，显示 <b>{a}</b> 个",
        "empty": "没有符合筛选条件的应用。",
        "rank_title": "排名趋势", "rank_sub": "前五名 · 每日最佳位置",
        "best_over": "在 {n} 天内观察到的最佳位置",
        "method_title": "方法说明", "faq_title": "得知一二",
        "footer_source_prefix": "数据来源：",
        "footer_tm": ("App Store 是 Apple Inc. 的商标，Google Play 是 Google LLC 的商标。"
                      "所有应用名称与标识均归各自所有者所有。"),
        "footer_note": ("最后更新 {updated}。排名为特定时点的采样，可能与实时商店排名有所不同。"),
        "home_eyebrow": "免费 · 付费 · 畅销 · 游戏",
        "home_title": "每日记录应用排行榜。",
        "home_sub": ("每日采集 App Store 与 Google Play 中 {n} 个市场的主要应用数据。每个页面都展示"
                     "当前排名、变动情况、排名趋势图，以及根据当日真实数据计算的简短洞察。"),
        "home_updated": "每日更新", "home_source_label": "数据来源：",
        "stat_markets": "市场", "stat_markets_sub": "全球商店地区",
        "stat_pages": "榜单页面", "stat_pages_sub": "已收录且每日更新",
        "stat_platforms": "平台", "stat_platforms_sub": "App Store & Google Play",
        "stat_snapshot": "最新采样", "stat_snapshot_sub": "每日更新数据",
        "browse_sub": "按市场与榜单类型浏览各个页面。",
        "mx_market": "市场", "mx_free": "免费榜", "mx_paid": "付费榜",
        "mx_grossing": "畅销榜", "mx_gfree": "游戏 · 免费",
        "mx_gpaid": "游戏 · 付费", "mx_ggrossing": "游戏 · 畅销",
        "methodology": ("本页对 {date} 日中国市场的 {ch}榜进行排名。数据来自官方商店排行榜的每日"
                        "采样，每日采集一次。排名变动与前一个有数据的日期比较。评分与开发者名称按"
                        "数据源原样展示。这是特定时点的采样，而非实时数据源。"),
        "faq": [
            ("这些数据多久更新一次？",
             "数据源每日发布新的采样。本页展示上方标注的最新可用日期。"),
            ("这是官方 App Store 排行榜吗？",
             "排名来自第三方开源数据集，源自官方商店排行榜，仅代表每日采样，而非实时商店。实时排名请查看官方商店。"),
            ("这些数据是你们所有的吗？",
             "不是。应用名称、图标与评分均归各自所有者所有。本页在标注数据来源并提供官方商店链接的前提下，展示事实的排名数据。"),
        ],
        "insight": {
            "frame": "截至 {date}，{mkt} {ch} Top {n} 中{new}；{mover}{dev}{genre}{top}",
            "new_low": "榜上 {n} 款为新增追踪",
            "new_high": "本次为该榜单的首次采样，日环比变动有限",
            "mover": "最大涨幅为 {name}（+{n} 位）。",
            "mover_none": "本次采样中无应用名次上升。",
            "dev": "{dev} 以 {n} 款入榜成为上榜产品最多的开发者。",
            "genre": "{genre} 类别占比最高（{n}/{total}）。",
            "top": "当前榜首为 {name}，评分 {rating}。",
        },
    },

    "tr": {
        "h1_chart": "{mkt} {ch} — {date}", "title_chart": "{mkt} {ch} ({date}) | {site}",
        "label": "Turkish", "native": "Türkçe", "html_lang": "tr",
        "brand_tag": "· Günlük uygulama sıralama dizini",
        "nav_home": "Ana sayfa", "lang_label": "Dil",
        "lang_partial_hint": "Bu dil yalnızca kendi pazarının sayfalarını kapsar",
        "hero_eyebrow_chart": "Günlük sıralama",
        "hero_sub_chart": ("Önde gelen uygulamaların güncel sırası, günlük değişim, geçmiş konum "
                           "ve gerçek verilerden hesaplanan içgörüler tek bakışta."),
        "meta_last_updated": "Son güncelleme", "meta_source": "Kaynak",
        "meta_longest_streak": "En uzun seri", "days": "gün",
        "insight_label": "Bugün ne değişti",
        "stat_1": "Şimdi 1 numara", "stat_2": "Bu anlık görüntüde yeni",
        "stat_3": "En büyük yükseliş", "stat_4": "En çok uygulama çıkaran geliştirici",
        "stat_2_sub": "listeye giren uygulamalar", "stat_3_none": "değişim yok",
        "stat_spots": "sıra", "stat_apps_board": "uygulama listeleniyor",
        "tbl_title": "Şimdi önde gelen uygulamalar",
        "tbl_sub": "Ara, harekete göre filtrele veya sıralamak için bir sütuna tıkla.",
        "search_ph": "Uygulama veya geliştiriciye göre filtrele…",
        "seg_all": "Tümü", "seg_up": "Yükselenler", "seg_down": "Düşenler", "seg_new": "Yeni",
        "th_rank": "#", "th_app": "Uygulama", "th_developer": "Geliştirici",
        "th_category": "Kategori", "th_rating": "Puan", "th_move": "Değişim",
        "count_fmt": "{b} uygulamadan <b>{a}</b> tanesi gösteriliyor",
        "empty": "Filtrelerle eşleşen uygulama yok.",
        "rank_title": "Sıra geçmişi", "rank_sub": "ilk 5 · günlük en iyi sıra",
        "best_over": "{n} günlük gözlemde en iyi sıra",
        "method_title": "Yöntem", "faq_title": "Bilmeniz gerekenler",
        "footer_source_prefix": "Veri kaynağı:",
        "footer_tm": ("App Store, Apple Inc.'in ve Google Play, Google LLC'nin ticari markasıdır. "
                      "Tüm uygulama adları ve markaları ilgili sahiplerine aittir."),
        "footer_note": ("Son güncelleme {updated}. Sıralamalar belirli bir anın örneğidir ve gerçek "
                        "zamanlı mağaza sırasından farklı olabilir."),
        "home_eyebrow": "Ücretsiz · Ücretli · Hasılat · Oyunlar",
        "home_title": "Uygulama sıralamaları, günlük takip.",
        "home_sub": ("App Store ve Google Play'de {n} pazarda önde gelen uygulamaların günlük anlık "
                     "görüntüleri. Her sayfada güncel sıralama, sıra değişimi, sıra geçmiş grafiği "
                     "ve o günün gerçek verilerinden hesaplanan kısa bir içgörü bulunur."),
        "home_updated": "Günlük güncellenir", "home_source_label": "Kaynak: ",
        "stat_markets": "Pazar", "stat_markets_sub": "dünya genelinde mağaza bölgesi",
        "stat_pages": "Sıralama sayfası", "stat_pages_sub": "dizinlenir ve günlük güncellenir",
        "stat_platforms": "Platform", "stat_platforms_sub": "App Store & Google Play",
        "stat_snapshot": "Son anlık görüntü", "stat_snapshot_sub": "her gün yeni veri",
        "browse_sub": "Pazar ve sıralama türüne göre sayfaları keşfedin.",
        "mx_market": "Pazar", "mx_free": "Ücretsiz", "mx_paid": "Ücretli",
        "mx_grossing": "Hasılat", "mx_gfree": "Oyunlar · Ücretsiz",
        "mx_gpaid": "Oyunlar · Ücretli", "mx_ggrossing": "Oyunlar · Hasılat",
        "methodology": ("Bu sayfa, {date} tarihinde {mkt} {ch} sıralamasındaki önde gelen uygulamaları "
                        "gösterir. Veriler resmi mağaza sıralamalarının günlük anlık görüntüsünden alınır "
                        "ve günde bir kez örneklenir. Sıra değişimi önceki günle karşılaştırılır. Puanlar "
                        "ve geliştirici adları kaynakta verildiği gibi gösterilir. Bu, gerçek zamanlı bir "
                        "akış değil, belirli bir anın örneğidir."),
        "faq": [
            ("Bu veriler ne sıklıkla güncelleniyor?",
             "Kaynak veri kümesi her gün yeni bir anlık görüntü yayınlar. Bu sayfa yukarıda gösterilen en son tarihi gösterir."),
            ("Bu resmi App Store sıralaması mı?",
             "Sıralamalar, üçüncü taraf açık veri kümesi aracılığıyla resmi mağaza sıralamalarından alınan günlük bir örnektir, canlı mağaza değildir. Gerçek zamanlı sıra için resmi mağazaya bakın."),
            ("Bu verilerin telif hakkı size mi ait?",
             "Hayır. Uygulama adları, simgeler ve puanlar ilgili sahiplerine aittir. Bu sayfa kaynağı belirterek ve resmi mağazalara bağlantı vererek gerçek sıralama verilerini sunar."),
        ],
        "insight": {
            "frame": "{date} itibariyle {mkt} {ch} Top {n} içinde {new}{mover}{dev}{genre}{top}",
            "new_low": "listelenen uygulamalardan {n} tanesi yeni olarak izleniyor",
            "new_high": "çok sayıda kayıt ilk kez gözlemleniyor, bu nedenle günlük hareket sınırlı",
            "mover": "En büyük yükseliş {name} oldu (+{n} sıra). ",
            "mover_none": "Bu görüntüde sırası yükselen uygulama olmadı. ",
            "dev": "{dev}, listede {n} uygulamayla en çok yer alan geliştirici. ",
            "genre": "{genre} kategorisi {n}/{total} ile en yüksek paya sahip. ",
            "top": "Şu an 1 numara {name}, puanı {rating}.",
        },
    },
}


def get(lang: str) -> dict:
    return LOCALES.get(lang, LOCALES["en"])


def languages_for_market(market: str) -> list[str]:
    """给定市场，返回所有提供该市场页面的语言（含 en）。"""
    out = ["en"]
    for lang, markets in LANG_MARKETS.items():
        if market in markets:
            out.append(lang)
    return out
