"""Central configuration: tickers, layers, display names, Hebrew strings, flag thresholds."""

from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
PROJECT_ROOT   = Path(__file__).parent.parent
PORTFOLIO_FILE = PROJECT_ROOT / "portfolio.json"

# ── Portfolio layers ───────────────────────────────────────────────────────────
TICKERS_BY_LAYER = {
    "Core (50%)":             ["VOO"],
    "Physical Infrastructure": ["CCJ", "FCX", "ETN", "VRT"],
    "Compute & Platform":      ["AMD", "AMZN", "GOOGL"],
    "Security & Stability":    ["CRWD", "ESLT", "TEVA", "EQX"],
}

LAYER_COLORS = {
    "Core (50%)":             "#00cf8d",
    "Physical Infrastructure": "#FF9800",
    "Compute & Platform":      "#2196F3",
    "Security & Stability":    "#9C27B0",
}

TICKER_NAMES = {
    "VOO":   "Vanguard S&P 500 ETF",
    "CCJ":   "Cameco — אורניום",
    "FCX":   "Freeport-McMoRan — נחושת",
    "ETN":   "Eaton — תשתיות חשמל",
    "VRT":   "Vertiv — קירור מרכזי נתונים",
    "AMD":   "Advanced Micro Devices",
    "AMZN":  "Amazon",
    "GOOGL": "Alphabet (Google)",
    "CRWD":  "CrowdStrike — סייבר",
    "ESLT":  "אלביט מערכות",
    "TEVA":  "טבע תעשיות פרמצבטיות",
    "EQX":   "Equinox Gold — זהב",
}

# Tickers with limited/no US analyst coverage — expected to have sparse data
KNOWN_LIMITED_TICKERS = {"ESLT"}

# Sector ETF benchmarks for relative-strength computation
SECTOR_ETFS = {
    "Core (50%)":             "SPY",
    "Physical Infrastructure": "XLI",
    "Compute & Platform":      "XLK",
    "Security & Stability":    "XLP",
}

# ── Red flag thresholds ────────────────────────────────────────────────────────
FLAG_THRESHOLDS = {
    "VOO":  {"drop_pct_warn": 7.0,   "drop_pct_trigger": 10.0},
    "CCJ":  {"uranium_warn":  85.0,  "uranium_trigger":  80.0},
    "FCX":  {"copper_warn":   4.5,   "copper_trigger":   4.2},
    "TEVA": {"price_warn":    15.0,  "price_trigger":    14.0},
    "EQX":  {"gold_warn":     4200.0,"gold_trigger":     4000.0},
    # Analyst-proxy flags — thresholds applied to derived signals
    "_proxy": {
        "drop_pct_watch":    12.0,
        "drop_pct_trigger":  20.0,
        "sell_frac_watch":   0.15,
        "sell_frac_trigger": 0.30,
        "downgrade_watch":   1,
        "downgrade_trigger": 3,
    },
    # Portfolio-level flags
    "_portfolio": {
        "voo_min_pct_warn":    45.0,
        "voo_min_pct_trigger": 40.0,
        "major_sell_warn":     1,
        "major_sell_trigger":  2,
    },
}

MAJOR_FIRMS = {
    "jpmorgan", "jp morgan", "goldman sachs", "goldman",
    "morgan stanley", "bank of america", "bofa", "merrill",
    "citi", "citigroup", "ubs", "rbc", "barclays",
    "wells fargo", "deutsche", "hsbc", "jefferies",
    "mizuho", "cowen", "td cowen", "oppenheimer",
    "bernstein", "piper sandler", "needham", "raymond james",
    "keybanc", "stifel", "wedbush",
}

SELL_GRADES = {"sell", "underperform", "underweight", "reduce"}

# ── Macro symbols ──────────────────────────────────────────────────────────────
MACRO_SYMBOLS = {
    "vix":       "^VIX",
    "yield_10y": "^TNX",
    "dxy":       "DX-Y.NYB",
}

COMMODITY_SYMBOLS = {
    "gold":    ("GC=F",  None),    # USD/oz — no scaling needed
    "copper":  ("HG=F",  100.0),   # quoted in cents/lb when >$20 → divide
    "uranium": ("UX1=F", None),    # USD/lb
}

# ── Hebrew display strings ─────────────────────────────────────────────────────
HE = {
    # Tabs
    "tab_overview":      "סקירה",
    "tab_portfolio":     "תיק שלי",
    "tab_charts":        "גרפים",
    "tab_analysts":      "אנליסטים",
    "tab_fundamentals":  "פונדמנטלס",
    "tab_red_flags":     "דגלים אדומים",
    "tab_news":          "חדשות",
    # Market status
    "market_open":       "פתוח",
    "market_pre":        "טרום מסחר",
    "market_after":      "אחרי שעות",
    "market_weekend":    "סוף שבוע",
    "market_holiday":    "חג",
    "market_closed_msg": "שוק סגור — מציג נתוני סגירה אחרונים",
    # Red flag statuses
    "flag_triggered":    "🔴 מופעל",
    "flag_watch":        "🟡 מעקב",
    "flag_ok":           "🟢 תקין",
    "flag_nodata":       "⚫ אין נתונים",
    # Sidebar
    "sidebar_header":    "מצב שוק",
    "refresh_btn":       "🔄 רענן נתונים",
    "refresh_disabled":  "השוק סגור — הנתונים הם מהסגירה האחרונה",
    "flags_all_ok":      "🟢 כל הדגלים תקינים",
    # Common labels
    "price":             "מחיר",
    "change":            "שינוי",
    "beta":              "בטא",
    "upside":            "אפסייד",
    "target":            "יעד אנליסטים",
    "consensus":         "קונצנזוס",
    "pnl":               "רווח/הפסד",
    "shares":            "מניות",
    "buy_date":          "תאריך קנייה",
    "buy_price":         "מחיר קנייה",
    "cost":              "עלות",
    "value":             "שווי",
    "layer":             "שכבה",
    "no_data":           "אין נתונים",
    "loading":           "טוען...",
    # Fundamentals
    "pe":                "P/E",
    "fwd_pe":            "P/E קדימה",
    "eps":               "EPS (TTM)",
    "roe":               "ROE",
    "market_cap":        "שווי שוק",
    "short_float":       "Short Float",
    "inst_own":          "בעלות מוסדית",
    "sector":            "סקטור",
    "div_yield":         "תשואת דיבידנד",
    "ex_date":           "תאריך ex-dividend",
    # Macro
    "vix":               "VIX (פחד)",
    "yield_10y":         "תשואה 10Y",
    "dxy":               "דולר (DXY)",
    # Charts
    "chart_title":       "גרף שנה — ",
    "rsi_label":         "RSI(14)",
    "volume_label":      "נפח מסחר",
    "sma20":             "SMA 20",
    "sma50":             "SMA 50",
    "sma200":            "SMA 200",
    "bollinger":         "Bollinger Bands",
    "high_52w":          "שיא 52 שבוע",
    "low_52w":           "שפל 52 שבוע",
    "analyst_target":    "יעד אנליסטים",
    "rel_strength":      "חוזק יחסי vs VOO",
    # Earnings
    "earnings_date":     "תאריך דוח רווחים",
    "days_to_earnings":  "ימים לדוח",
    "eps_beat":          "הכה תחזית",
    "eps_miss":          "פספס תחזית",
}

# ── Stock suggestions (curated complementary picks) ───────────────────────────
# Each entry: ticker, name, theme (Hebrew), rationale (Hebrew), complements (list of portfolio tickers)
SUGGESTIONS = [
    {
        "ticker":     "NVDA",
        "name":       "NVIDIA",
        "theme":      "AI GPU — מנוע ה-AI",
        "rationale":  "NVDA מספקת את ה-GPU שמריץ את כל מודלי ה-AI. משלימה את AMD ו-AMZN (AWS) שניהם לקוחות/מתחרים גדולים.",
        "complements": ["AMD", "AMZN", "GOOGL"],
    },
    {
        "ticker":     "MSFT",
        "name":       "Microsoft",
        "theme":      "ענן + AI — Azure & Copilot",
        "rationale":  "Azure מתחרה ישיר ל-AWS של AMZN. Copilot + OpenAI מתחרה ל-GOOGL. מוסיף חשיפה לענן מוסדי עם מאזן חזק.",
        "complements": ["AMZN", "GOOGL"],
    },
    {
        "ticker":     "PANW",
        "name":       "Palo Alto Networks",
        "theme":      "סייבר — פלטפורמה משולבת",
        "rationale":  "ספקית פלטפורמת סייבר מוביל. פיזור סיכון טוב ל-CRWD — מגזר הסייבר עם שחקן שני חזק.",
        "complements": ["CRWD"],
    },
    {
        "ticker":     "TSM",
        "name":       "Taiwan Semiconductor",
        "theme":      "שבבים — יצרנית מובילה",
        "rationale":  "TSMC מייצרת שבבים עבור AMD, NVDA, Apple ועוד. חשיפה לכלל תעשיית השבבים ללא סיכון תחרותי ישיר.",
        "complements": ["AMD"],
    },
    {
        "ticker":     "NXE",
        "name":       "NexGen Energy",
        "theme":      "אורניום — פרויקט Arrow",
        "rationale":  "חברת אורניום קנדית עם מרבץ Arrow — אחד הגדולים בעולם. מגדיל חשיפה לאורניום בצד CCJ עם פוטנציאל צמיחה גבוה יותר.",
        "complements": ["CCJ"],
    },
    {
        "ticker":     "WPM",
        "name":       "Wheaton Precious Metals",
        "theme":      "זהב — סטרימינג, סיכון נמוך",
        "rationale":  "חברת סטרימינג — רוכשת זכויות על כריה עתידית במחיר קבוע. חשיפה לזהב עם סיכון תפעולי נמוך משמעותית מ-EQX.",
        "complements": ["EQX"],
    },
    {
        "ticker":     "META",
        "name":       "Meta Platforms",
        "theme":      "AI + פלטפורמה — Llama & Ads",
        "rationale":  "משקיעה מסיבית ב-AI (Llama), מודל הכנסות מפרסום חזק. משלימה את GOOGL ו-AMZN בחשיפה לפלטפורמות הדיגיטליות הגדולות.",
        "complements": ["GOOGL", "AMZN"],
    },
]

# ── Theme colors ───────────────────────────────────────────────────────────────
COLOR = {
    "primary":   "#00cf8d",
    "positive":  "#4CAF50",
    "negative":  "#F44336",
    "warning":   "#FF9800",
    "neutral":   "#9E9E9E",
    "dim":       "#9ca3af",
    "bg_red":    "#2d0a0a",
    "bg_orange": "#2a1800",
    "bg_dark":   "#1a1a2a",
    "text_dim":  "#aaaaaa",
}
