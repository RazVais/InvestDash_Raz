"""Central configuration: tickers, layers, display names, Hebrew strings, flag thresholds."""

from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
PROJECT_ROOT   = Path(__file__).parent.parent
PORTFOLIO_FILE = PROJECT_ROOT / "portfolio.json"

# ── Portfolio layers ───────────────────────────────────────────────────────────
TICKERS_BY_LAYER = {
    "Core (50%)":             ["VOO"],
    "Physical Infrastructure": ["CCJ", "FCX", "ETN", "VRT", "EQX"],
    "Compute & Platform":      ["AMD", "AMZN", "GOOGL"],
    "Security & Stability":    ["XAR", "CRWD", "ESLT"],
    "Healthcare & Pharma":     ["TEVA"],
}

LAYER_COLORS = {
    "Core (50%)":             "#00cf8d",
    "Physical Infrastructure": "#FF9800",
    "Compute & Platform":      "#2196F3",
    "Security & Stability":    "#9C27B0",
    "Healthcare & Pharma":     "#E91E63",
}

# Reverse map: ticker → layer.  Built from TICKERS_BY_LAYER + extended coverage.
# Used by guess_layer() to auto-assign the layer when the user adds a new position.
TICKER_LAYER_MAP: dict = {}
for _layer, _tickers in TICKERS_BY_LAYER.items():
    for _t in _tickers:
        TICKER_LAYER_MAP[_t] = _layer

# Extended coverage: suggestions, common ETFs, and well-known stocks
_EXTRA_LAYERS = {
    # ── Suggestions ──────────────────────────────────────────────
    "NVDA":  "Compute & Platform",
    "MSFT":  "Compute & Platform",
    "PANW":  "Security & Stability",
    "TSM":   "Compute & Platform",
    "NXE":   "Physical Infrastructure",
    "WPM":   "Security & Stability",
    "META":  "Compute & Platform",
    # ── Common ETFs / indices → Core ─────────────────────────────
    "SPY":   "Core (50%)",
    "IVV":   "Core (50%)",
    "VTI":   "Core (50%)",
    "QQQ":   "Core (50%)",
    "SCHB":  "Core (50%)",
    "VEA":   "Core (50%)",
    "VWO":   "Core (50%)",
    "GLD":   "Core (50%)",
    "IAU":   "Core (50%)",
    "BND":   "Core (50%)",
    "AGG":   "Core (50%)",
    # ── Tech / AI / Semiconductors → Compute & Platform ──────────
    "AAPL":  "Compute & Platform",
    "INTC":  "Compute & Platform",
    "QCOM":  "Compute & Platform",
    "AVGO":  "Compute & Platform",
    "MU":    "Compute & Platform",
    "ASML":  "Compute & Platform",
    "ORCL":  "Compute & Platform",
    "IBM":   "Compute & Platform",
    "CRM":   "Compute & Platform",
    "SNOW":  "Compute & Platform",
    "PLTR":  "Compute & Platform",
    "TSLA":  "Compute & Platform",
    "UBER":  "Compute & Platform",
    "SHOP":  "Compute & Platform",
    # ── Energy / Materials / Infrastructure ──────────────────────
    "XOM":   "Physical Infrastructure",
    "CVX":   "Physical Infrastructure",
    "NEE":   "Physical Infrastructure",
    "LIN":   "Physical Infrastructure",
    "NUE":   "Physical Infrastructure",
    "FCX":   "Physical Infrastructure",
    "MP":    "Physical Infrastructure",
    "DNN":   "Physical Infrastructure",
    "URA":   "Physical Infrastructure",
    "AGX":   "Physical Infrastructure",
    # ── Defense / Healthcare / Gold / Cyber → Security & Stability
    "LMT":   "Security & Stability",
    "RTX":   "Security & Stability",
    "NOC":   "Security & Stability",
    "BA":    "Security & Stability",
    "GD":    "Security & Stability",
    "FTNT":  "Security & Stability",
    "S":     "Security & Stability",
    "ZS":    "Security & Stability",
    "OKTA":  "Security & Stability",
    "JNJ":   "Security & Stability",
    "PFE":   "Security & Stability",
    "MRK":   "Security & Stability",
    "ABBV":  "Security & Stability",
    "GFI":   "Security & Stability",
    "AEM":   "Security & Stability",
    "NEM":   "Security & Stability",
}
TICKER_LAYER_MAP.update(_EXTRA_LAYERS)

# Common ETF suffixes / keywords for detection of unknown ETF tickers
_ETF_KEYWORDS = ("etf", "fund", "trust", "index", "ishares", "vanguard", "spdr", "invesco")


def guess_layer(ticker: str) -> str:
    """Return the most likely portfolio layer for *ticker*.

    Priority:
    1. Exact match in TICKER_LAYER_MAP
    2. Ticker ends with a common ETF suffix (e.g. 'F' after a dot, all-caps 3-4 chars like SPY style)
    3. Default → "Compute & Platform" (most common new additions)
    """
    t = ticker.upper().strip()
    if t in TICKER_LAYER_MAP:
        return TICKER_LAYER_MAP[t]
    # Heuristic: ETF tickers often end in specific letters or contain known fund families
    for kw in _ETF_KEYWORDS:
        if kw in t.lower():
            return "Core (50%)"
    return "Compute & Platform"


TICKER_NAMES = {
    "VOO":   "Vanguard S&P 500 ETF",
    "XAR":   "SPDR S&P Aerospace & Defense ETF",
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

# ETFs in the portfolio — no P/E, ROE, EPS etc. (no earnings, no equity returns)
PORTFOLIO_ETFS = {"VOO", "XAR"}

# Sector ETF benchmarks for relative-strength computation
SECTOR_ETFS = {
    "Core (50%)":             "SPY",
    "Physical Infrastructure": "XLI",
    "Compute & Platform":      "XLK",
    "Security & Stability":    "XAR",
    "Healthcare & Pharma":     "XLV",
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

# ── Static company briefs ─────────────────────────────────────────────────────
# Shown in the news tab. Hebrew text — displayed RTL in the UI.
TICKER_BRIEFS = {
    "XAR": (
        "XAR (SPDR S&P Aerospace & Defense ETF) עוקב אחרי מדד S&P Aerospace & Defense — "
        "המורכב מחברות הביטחון, תעופה ואוויריות הגדולות בארה\"ב. "
        "הוא כולל ניירות כמו RTX, LMT, NOC, GD ו-L3Harris, הנהנות מהגידול בתקציבי NATO ומשרד ההגנה האמריקאי. "
        "XAR משמש כנקודת ייחוס (Ground Zero) לשכבת האבטחה והביטחון בתיק — "
        "ביצועי CRWD ו-ESLT נמדדים אל מולו, כשם ש-VOO משמש כנקודת ייחוס לשוק הרחב."
    ),
    "VOO": (
        "קרן הסל Vanguard S&P 500 עוקבת אחרי מדד S&P 500 — 500 החברות הגדולות בארה\"ב לפי שווי שוק. "
        "עם דמי ניהול של 0.03% בלבד, היא אחת מקרנות המניות הזולות והנזילות ביותר בעולם. "
        "החשיפה הענפית מובלת על ידי טכנולוגיה (~30%), בריאות (~13%) ופיננסים (~13%)."
    ),
    "CCJ": (
        "Cameco היא יצרנית האורניום הציבורית הגדולה בעולם, ומשדרת מסצ'ואן, קנדה. "
        "היא מפעילה את מכרות McArthur River וCigar Lake — בין מרבצי האורניום באיכות הגבוהה ביותר בכדור הארץ. "
        "Cameco מחזיקה ב-49% מ-Westinghouse Electric, ספקית דלק גרעיני ושירותים מרכזית, המעניקה לה חשיפה לתחייה הגרעינית העולמית."
    ),
    "FCX": (
        "Freeport-McMoRan היא יצרנית הנחושת הציבורית הגדולה בעולם, עם מכרות ברחבי האמריקות ואינדונזיה (Grasberg — מכרה הנחושת-זהב הגדול בעולם). "
        "החברה מהווה הימור ישיר על מעבר האנרגיה: הביקוש לנחושת צפוי להכפיל עצמו עד 2035 עקב כלי רכב חשמליים, תשתיות רשת ומרכזי נתונים. "
        "בנוסף, היא מייצרת זהב ומוליבדן כתוצרי לוואי."
    ),
    "ETN": (
        "Eaton Corporation היא חברה תעשייתית מגוונת המתמקדת בניהול חשמל, הידראוליקה ומערכות רכב. "
        "היא נהנית ממגמות מודרניזציה של הרשת החשמלית, חשמול ועלייה בביקוש לחשמל ממרכזי נתונים. "
        "פלח החשמל (~60% מהכנסות) כולל ציוד מיתוג, מפסקים ומערכות UPS המשמשים חברות ענן גדולות וחברות חשמל."
    ),
    "VRT": (
        "Vertiv מעצבת ומייצרת תשתית דיגיטלית קריטית — ניהול חום, אספקת חשמל ותשתיות IT למרכזי נתונים. "
        "פתרונות הקירור שלה (מיזוג אוויר מדויק, קירור נוזלי) הם מרכזיים לבנייה של מרכזי נתונים לבינה מלאכותית, שבהם GPU מייצרים פי 5-10 יותר חום משרתים רגילים. "
        "לקוחות מרכזיים כוללים את AWS, Azure, Google ומפעילי מרכזי מיקום-משותף."
    ),
    "AMD": (
        "Advanced Micro Devices מעצבת מעבדים (EPYC לשרתים, Ryzen למחשבים אישיים) ומעבדי גרפיקה (סדרת Instinct MI לעומסי AI ו-HPC). "
        "ה-GPU MI300X הוא התחרות העיקרית ל-H100/H200 של NVIDIA באימון ובהסקת בינה מלאכותית. "
        "AMD גם מספקת שבבים מותאמים אישית (CDNA) ל-Microsoft Azure ול-Meta עבור מאיצי AI."
    ),
    "AMZN": (
        "Amazon היא שוק המסחר האלקטרוני הגדול בעולם וספקית הענן המובילה דרך AWS (~33% נתח שוק ענן). "
        "AWS מייצרת את רוב ההכנסה התפעולית של Amazon ומפעילה שירותי AI כולל Bedrock, SageMaker ושבבי Trainium/Inferentia. "
        "Amazon מפעילה גם את רשת הלוגיסטיקה הגדולה בעולם ועסק פרסום דיגיטלי הצומח במהירות."
    ),
    "GOOGL": (
        "Alphabet (Google) מפעילה את מנוע החיפוש הדומיננטי בעולם (~90% נתח שוק), YouTube ו-Google Cloud Platform (GCP). "
        "Google Cloud היא ספקית הענן השלישית בגודלה וצומחת מהר יותר מ-AWS ו-Azure. "
        "DeepMind ו-Google Brain הם זרועות מחקר ה-AI של Alphabet; Gemini הוא מודל ה-AI הדגל המתחרה בסדרת GPT של OpenAI."
    ),
    "CRWD": (
        "CrowdStrike מספקת אבטחת סייבר מבוססת ענן דרך פלטפורמת Falcon, המשתמשת ב-AI לזיהוי ומניעת איומים על נקודות קצה, ענן וזהות. "
        "הסוכן שלה מותקן על מערכות כ-24,000 לקוחות, ומייצר גרף מודיעין איומים קנייני המשתפר עם הגדלה. "
        "CrowdStrike היא מובילת השוק ב-EDR (זיהוי ותגובה בנקודות קצה) עם אסטרטגיה גוברת של איחוד פלטפורמה."
    ),
    "ESLT": (
        "אלביט מערכות היא חברת האלקטרוניקה הביטחונית הגדולה ביותר בישראל, הנסחרת הן בנאסד\"ק והן בבורסה בתל אביב. "
        "היא מספקת מערכות צבאיות (כלי טיס בלתי מאוישים, אלקטרו-אופטיקה, C4I, ארטילריה) ליותר מ-100 מדינות, כולל חברות נאט\"ו וצה\"ל. "
        "הסביבה הגיאופוליטית הנוכחית והגידול בהוצאות ביטחוניות עולמיות מהוות רוחות גב מבניות לספר ההזמנות של אלביט."
    ),
    "TEVA": (
        "טבע פארמצבטיקה היא יצרנית התרופות הגנריות הגדולה בעולם, ומשדרת בתל אביב. "
        "תיק המוצרים הממותגים שלה כולל את Austedo (דיסקינזיה עיכובית) ו-Ajovy (מיגרנות), כאשר Austedo צומח במהירות. "
        "טבע השלימה מחזור גדול של ארגון מחדש של חובות ומבצעת אסטרטגיית 'Pivot to Growth' המתמקדת בתרופות גנריות מורכבות ותרופות חדשניות."
    ),
    "EQX": (
        "Equinox Gold היא יצרנית זהב קנדית עם 10 מכרות פעילים ברחבי האמריקות, המייצרת כ-700 אלף אונקיות לשנה. "
        "היא הימור ממונף על זהב — ההכנסות רגישות מאוד למחיר הזהב, הנהנה מאינפלציה, חולשת דולר ותיאבון סיכון נמוך. "
        "מכרה Greenstone של Equinox באונטריו החל לפעול ב-2024 וצפוי להפוך לאחד ממכרות הזהב הגדולים בקנדה."
    ),
    "AGX": (
        "Argan Inc. היא חברת אחזקות שחברת הבת העיקרית שלה, Gemma Power Systems, בונה תחנות כוח גז טבעי ואנרגיה מתחדשת בחוזי EPC במחיר קבוע. "
        "היא נהנית מהרחבת תשתיות האנרגיה האמריקאית המונעת על ידי ביקוש חשמלי ממרכזי נתונים ומודרניזציה של הרשת. "
        "Argan אינה נושאת בחוב ומחזיקה ביתרת מזומנים משמעותית ביחס לשווי השוק שלה."
    ),
}

# ── Static sector / industry labels ───────────────────────────────────────────
TICKER_SECTOR = {
    "VOO":   ("ETFs", "Broad Market"),
    "XAR":   ("Defense", "Aerospace & Defense ETF"),
    "CCJ":   ("Energy", "Uranium Mining"),
    "FCX":   ("Materials", "Copper Mining"),
    "ETN":   ("Industrials", "Electrical Equipment"),
    "VRT":   ("Technology", "Data Centre Infrastructure"),
    "AMD":   ("Technology", "Semiconductors"),
    "AMZN":  ("Consumer Discretionary / Technology", "E-Commerce & Cloud"),
    "GOOGL": ("Communication Services", "Internet & AI"),
    "CRWD":  ("Technology", "Cybersecurity"),
    "ESLT":  ("Defense", "Defense Electronics"),
    "TEVA":  ("Healthcare", "Pharmaceuticals (Generics)"),
    "EQX":   ("Materials", "Gold Mining"),
    "AGX":   ("Industrials", "Power Plant EPC"),
}

# ── Main competitors per ticker ───────────────────────────────────────────────
# Used in the news tab company brief. Format: {ticker: [(symbol, display_name), ...]}
TICKER_PEERS = {
    "VOO":   [("SPY", "SPDR S&P 500"), ("IVV", "iShares S&P 500"), ("QQQ", "Invesco NASDAQ-100")],
    "XAR":   [("ITA", "iShares U.S. Aerospace & Defense ETF"), ("LMT", "Lockheed Martin"), ("RTX", "RTX Corp (Raytheon)")],
    "CCJ":   [("NXE", "NexGen Energy"), ("URA", "Global X Uranium ETF"), ("DNN", "Denison Mines")],
    "FCX":   [("SCCO", "Southern Copper"), ("BHP", "BHP Group"), ("TECK", "Teck Resources")],
    "ETN":   [("EMR", "Emerson Electric"), ("ROK", "Rockwell Automation"), ("ABB", "ABB Ltd")],
    "VRT":   [("DELL", "Dell Technologies"), ("HPE", "Hewlett Packard Enterprise"), ("JCI", "Johnson Controls")],
    "AMD":   [("NVDA", "NVIDIA"), ("INTC", "Intel"), ("QCOM", "Qualcomm")],
    "AMZN":  [("MSFT", "Microsoft Azure"), ("GOOGL", "Google Cloud"), ("BABA", "Alibaba")],
    "GOOGL": [("MSFT", "Microsoft"), ("META", "Meta"), ("AMZN", "Amazon")],
    "CRWD":  [("PANW", "Palo Alto Networks"), ("S", "SentinelOne"), ("FTNT", "Fortinet")],
    "ESLT":  [("LMT", "Lockheed Martin"), ("RTX", "Raytheon"), ("BA", "Boeing")],
    "TEVA":  [("MYL", "Viatris"), ("PRGO", "Perrigo"), ("AGN", "Allergan")],
    "EQX":   [("GFI", "Gold Fields"), ("AEM", "Agnico Eagle"), ("WPM", "Wheaton Precious Metals")],
    "AGX":   [("PWR", "Quanta Services"), ("MTZ", "MasTec"), ("TTEK", "Tetra Tech")],
}

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
