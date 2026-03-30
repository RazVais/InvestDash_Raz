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

# ── Static company briefs ─────────────────────────────────────────────────────
# Shown in the news tab. English text — displayed LTR in the UI.
TICKER_BRIEFS = {
    "VOO": (
        "Vanguard S&P 500 ETF tracks the S&P 500 index — the 500 largest US companies by market cap. "
        "With an expense ratio of 0.03%, it is one of the lowest-cost and most liquid equity ETFs available. "
        "Sector exposure is dominated by Technology (~30%), Healthcare (~13%), and Financials (~13%)."
    ),
    "CCJ": (
        "Cameco Corporation is the world's largest publicly traded uranium producer, headquartered in Saskatoon, Canada. "
        "It operates the McArthur River/Key Lake and Cigar Lake mines — among the highest-grade uranium deposits on Earth. "
        "Cameco also holds a 49% stake in Westinghouse Electric, a major nuclear fuel and services company, providing leverage to the nuclear renaissance."
    ),
    "FCX": (
        "Freeport-McMoRan is the world's largest publicly traded copper producer, with mines across the Americas and Indonesia (Grasberg — the world's largest copper-gold mine). "
        "The company is a direct play on the energy transition: copper demand is expected to double by 2035 driven by EVs, grid infrastructure, and data centers. "
        "It also produces gold and molybdenum as byproducts."
    ),
    "ETN": (
        "Eaton Corporation is a diversified industrial company focused on electrical power management, hydraulics, and vehicle systems. "
        "It is a key beneficiary of grid modernisation, electrification, and data-centre power demand. "
        "The electrical segment (~60% of revenue) includes switchgear, circuit breakers, and UPS systems used by hyperscalers and utilities."
    ),
    "VRT": (
        "Vertiv Holdings designs and manufactures critical digital infrastructure — thermal management, power, and IT infrastructure for data centres. "
        "Its cooling solutions (precision air conditioning, liquid cooling) are central to AI data-centre buildouts, where GPUs generate 5–10× more heat than traditional servers. "
        "Major customers include hyperscalers (AWS, Azure, Google) and colocation providers."
    ),
    "AMD": (
        "Advanced Micro Devices designs CPUs (EPYC for servers, Ryzen for desktops) and GPUs (Instinct MI series for AI/HPC workloads). "
        "Its MI300X GPU is the primary competition to NVIDIA's H100/H200 in AI training and inference. "
        "AMD also supplies custom silicon (CDNA) to Microsoft Azure and Meta for AI accelerators."
    ),
    "AMZN": (
        "Amazon is the world's largest e-commerce marketplace and the leading cloud provider through AWS (~33% cloud market share). "
        "AWS generates the majority of Amazon's operating income and powers AI services including Bedrock, SageMaker, and Trainium/Inferentia chips. "
        "Amazon also operates the world's largest logistics network and a fast-growing advertising business."
    ),
    "GOOGL": (
        "Alphabet (Google) operates the world's dominant search engine (~90% market share), YouTube, and Google Cloud Platform (GCP). "
        "Google Cloud is the third-largest cloud provider and is growing faster than AWS/Azure. "
        "DeepMind and Google Brain are Alphabet's AI research arms; Gemini is its flagship AI model competing with OpenAI's GPT series."
    ),
    "CRWD": (
        "CrowdStrike provides cloud-native cybersecurity through its Falcon platform, which uses AI to detect and prevent threats across endpoints, cloud, and identity. "
        "Its agent is installed on ~24,000 customers' systems, generating a proprietary threat-intelligence graph that improves with scale. "
        "CrowdStrike is the market leader in EDR (Endpoint Detection & Response) with a growing platform consolidation strategy."
    ),
    "ESLT": (
        "Elbit Systems is Israel's largest defense electronics company, listed on both NASDAQ and the Tel Aviv Stock Exchange. "
        "It supplies military systems (UAVs, electro-optics, C4I, artillery) to over 100 countries, including NATO members and Israel's IDF. "
        "The ongoing geopolitical environment and global defence spending increases are structural tailwinds for Elbit's order book."
    ),
    "TEVA": (
        "Teva Pharmaceutical is the world's largest generic drug manufacturer, headquartered in Tel Aviv. "
        "Its branded portfolio includes Austedo (tardive dyskinesia) and Ajovy (migraines), with Austedo growing rapidly. "
        "Teva completed a major debt-restructuring cycle and is executing a 'Pivot to Growth' strategy focused on complex generics and innovative medicines."
    ),
    "EQX": (
        "Equinox Gold is a Canadian gold producer with 10 operating mines across the Americas, producing ~700k oz/year. "
        "It is a leveraged gold play — revenues are highly sensitive to the gold price, which benefits from inflation, dollar weakness, and risk-off sentiment. "
        "Equinox's Greenstone mine in Ontario ramped up in 2024 and is expected to become one of Canada's largest gold mines."
    ),
    "AGX": (
        "Argan Inc. is a holding company whose primary subsidiary Gemma Power Systems builds natural gas and renewable power plants under fixed-price EPC (Engineering, Procurement, Construction) contracts. "
        "It benefits from the US energy infrastructure buildout driven by data-centre power demand and grid modernisation. "
        "Argan carries no debt and maintains a significant cash position relative to its market cap."
    ),
}

# ── Static sector / industry labels ───────────────────────────────────────────
TICKER_SECTOR = {
    "VOO":   ("ETFs", "Broad Market"),
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
