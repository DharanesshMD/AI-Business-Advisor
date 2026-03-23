"""
Scrapling Site Registry — domain → fetcher type + CSS selectors + categories.

Each site entry defines:
  - fetcher: "plain" (fast HTTP) or "stealthy" (browser with anti-bot bypass)
  - selectors: ordered list of CSS selectors for content extraction
  - categories: which query categories this site is relevant for
"""

from typing import TypedDict


class SiteConfig(TypedDict, total=False):
    fetcher: str            # "plain" or "stealthy"
    selectors: list[str]    # CSS selectors for article content (tried in order)
    categories: list[str]   # Query categories this site serves


# ──────────────────────────────────────────────────────────────────
# Site Registry: domain → config
# ──────────────────────────────────────────────────────────────────

SITE_REGISTRY: dict[str, SiteConfig] = {
    # ─── Financial News ───
    "reuters.com": {
        "fetcher": "stealthy",
        "selectors": [
            "article .article-body__content",
            "article[class*='article'] p",
            ".article__body p",
            "article p",
        ],
        "categories": ["finance", "markets", "economy", "business"],
    },
    "bloomberg.com": {
        "fetcher": "stealthy",
        "selectors": [
            ".article-body__content p",
            "[class*='body-content'] p",
            "article p",
        ],
        "categories": ["finance", "markets", "economy", "startup", "business"],
    },
    "ft.com": {
        "fetcher": "stealthy",
        "selectors": [
            ".article__content-body p",
            "[class*='content-body'] p",
            "article p",
        ],
        "categories": ["finance", "markets", "economy", "business"],
    },

    # ─── Startup & Tech ───
    "techcrunch.com": {
        "fetcher": "plain",
        "selectors": [
            ".article-content p",
            ".entry-content p",
            "article p",
        ],
        "categories": ["startup", "technology", "funding", "business"],
    },
    "crunchbase.com": {
        "fetcher": "stealthy",
        "selectors": [
            "[class*='description'] p",
            ".overview-content p",
            "main p",
        ],
        "categories": ["startup", "funding", "company"],
    },

    # ─── Government / Regulatory ───
    "sec.gov": {
        "fetcher": "plain",
        "selectors": [
            "#content-main p",
            ".article-body p",
            "main p",
        ],
        "categories": ["regulation", "finance", "compliance", "filings"],
    },
    "sba.gov": {
        "fetcher": "plain",
        "selectors": [
            ".field--name-body p",
            ".usa-prose p",
            "main p",
        ],
        "categories": ["startup", "regulation", "business", "funding"],
    },
    "mca.gov.in": {
        "fetcher": "plain",
        "selectors": [
            ".field-item p",
            "#block-system-main p",
            "main p",
        ],
        "categories": ["regulation", "compliance", "business", "india"],
    },
    "incometax.gov.in": {
        "fetcher": "plain",
        "selectors": [
            ".inner-content p",
            "#ContentPlaceHolder p",
            "main p",
        ],
        "categories": ["tax", "regulation", "compliance", "india"],
    },

    # ─── Strategy / Consulting ───
    "hbr.org": {
        "fetcher": "stealthy",
        "selectors": [
            ".article-body p",
            "[class*='article'] p",
            "article p",
        ],
        "categories": ["strategy", "management", "business", "leadership"],
    },
    "mckinsey.com": {
        "fetcher": "stealthy",
        "selectors": [
            ".article-body p",
            "[class*='body-content'] p",
            "article p",
        ],
        "categories": ["strategy", "management", "consulting", "business"],
    },

    # ─── Indian Business ───
    "economictimes.indiatimes.com": {
        "fetcher": "plain",
        "selectors": [
            ".artText p",
            ".article-body p",
            ".Normal p",
            "article p",
        ],
        "categories": ["finance", "markets", "economy", "india", "business"],
    },
}


# ──────────────────────────────────────────────────────────────────
# Category → keyword mapping (used by _classify_query)
# ──────────────────────────────────────────────────────────────────

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "finance": [
        "stock", "share", "market", "invest", "portfolio", "dividend",
        "earnings", "revenue", "profit", "loss", "valuation", "IPO",
        "bond", "treasury", "interest rate", "inflation", "GDP",
        "financial", "banking", "insurance", "mutual fund", "ETF",
    ],
    "startup": [
        "startup", "founder", "venture capital", "seed", "series a",
        "series b", "funding", "pitch", "incubator", "accelerator",
        "unicorn", "MVP", "product-market fit", "bootstrapping",
        "angel investor", "equity", "cap table", "exit strategy",
    ],
    "regulation": [
        "regulation", "compliance", "license", "permit", "registration",
        "government", "policy", "law", "legal", "act", "ordinance",
        "SEC", "SEBI", "RBI", "FDA", "FTC", "GDPR", "SOX",
    ],
    "tax": [
        "tax", "GST", "income tax", "corporate tax", "deduction",
        "exemption", "filing", "audit", "IRS", "tax planning",
        "tax credit", "depreciation", "TDS", "ITR",
    ],
    "strategy": [
        "strategy", "business model", "competitive advantage", "pricing",
        "marketing", "growth", "scaling", "SaaS", "B2B", "B2C",
        "market entry", "SWOT", "Porter", "blue ocean", "disruption",
    ],
    "technology": [
        "AI", "machine learning", "software", "cloud", "SaaS", "API",
        "automation", "data", "blockchain", "crypto", "fintech",
        "cybersecurity", "platform", "app", "digital transformation",
    ],
    "markets": [
        "S&P 500", "Nasdaq", "Dow", "Nifty", "Sensex", "bull",
        "bear", "correction", "rally", "volatility", "hedge",
        "forex", "commodity", "crude oil", "gold", "silver",
    ],
    "economy": [
        "economy", "recession", "inflation", "GDP", "unemployment",
        "Federal Reserve", "central bank", "monetary policy", "fiscal",
        "trade deficit", "tariff", "supply chain", "macro",
    ],
    "india": [
        "India", "Indian", "Bharat", "rupee", "INR", "Nifty",
        "Sensex", "SEBI", "RBI", "GST", "MCA", "MSME", "UPI",
        "Aadhaar", "Mumbai", "Bangalore", "Delhi", "Chennai",
    ],
    "management": [
        "management", "leadership", "hiring", "team", "culture",
        "OKR", "KPI", "productivity", "remote work", "agile",
    ],
}


# ──────────────────────────────────────────────────────────────────
# Generic fallback selectors (used when site-specific ones fail)
# ──────────────────────────────────────────────────────────────────

GENERIC_SELECTORS: list[str] = [
    "article p",
    "main p",
    "[role='main'] p",
    ".content p",
    ".post-content p",
    ".entry-content p",
    "#content p",
    "body p",
]


def get_sites_for_categories(categories: list[str], max_sites: int = 5) -> dict[str, SiteConfig]:
    """Return the most relevant sites for the given categories (max `max_sites`)."""
    scored: list[tuple[str, SiteConfig, int]] = []
    for domain, config in SITE_REGISTRY.items():
        score = sum(1 for cat in categories if cat in config.get("categories", []))
        if score > 0:
            scored.append((domain, config, score))

    # Sort by relevance score descending, then alphabetically for determinism
    scored.sort(key=lambda x: (-x[2], x[0]))
    return {domain: config for domain, config, _ in scored[:max_sites]}
