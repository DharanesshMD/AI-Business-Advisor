"""
Scrapling Deep-Scraping Search Engine.

Two-phase approach:
  1. Discovery  — DDG finds URLs relevant to query (with site: operators for known sites)
  2. Extraction — Scrapling fetches full page content with CSS selectors

Graceful fallback chain: stealthy → plain fetcher, scrape fail → DDG snippets.
"""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from backend.config import get_settings
from backend.logger import get_logger
from backend.search.engines.scrapling_sites import (
    CATEGORY_KEYWORDS,
    GENERIC_SELECTORS,
    SITE_REGISTRY,
    get_sites_for_categories,
)
from backend.search.engines.scrapling_cache import (
    get_page_cache,
    get_query_cache,
    set_page_cache,
    set_query_cache,
)


class ScraplingEngine:
    """Deep-scraping search engine using Scrapling + DDG discovery."""

    def __init__(self):
        self.logger = get_logger()
        self.name = "scrapling"
        self.settings = get_settings()

    # ──────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────

    async def search(
        self,
        query: str,
        max_results: int = 5,
        category: Optional[str] = None,
    ) -> list[dict]:
        """
        Discover URLs via DDG then deep-scrape content with Scrapling.

        Returns:
            list[dict] with keys: title, url, content, source
        """
        self.logger.separator(f"SCRAPLING DEEP SCRAPE: {query}")
        start_time = time.time()

        # 1. Check query-level cache
        cached = get_query_cache(query)
        if cached:
            self.logger.debug(f"Scrapling returning {len(cached)} cached results")
            return cached

        try:
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                self._sync_search,
                query,
                max_results,
                category,
            )

            duration_ms = (time.time() - start_time) * 1000
            self.logger.api_response("Scrapling", 200, duration_ms)
            self.logger.debug(f"Scrapling returned {len(results)} deep-scraped results")

            # Cache the query results
            if results:
                set_query_cache(query, results)

            return results

        except Exception as e:
            self.logger.error("Scrapling search error", e)
            return self._fallback_duckduckgo(query, max_results)

    # ──────────────────────────────────────────────────────────────
    # Synchronous orchestration (runs in executor)
    # ──────────────────────────────────────────────────────────────

    def _sync_search(
        self,
        query: str,
        max_results: int,
        category: Optional[str],
    ) -> list[dict]:
        """Full search pipeline: classify → discover → scrape."""

        # 1. Classify query → pick relevant categories
        categories = self._classify_query(query, category)
        self.logger.debug(f"Scrapling classified query as: {categories}")

        # 2. Get relevant sites for those categories
        target_sites = get_sites_for_categories(categories, max_sites=5)
        self.logger.debug(f"Scrapling targeting {len(target_sites)} sites: {list(target_sites.keys())}")

        # 3. Discover URLs via DDG with site: operators
        discovered = self._discover_urls(query, target_sites, max_results)
        self.logger.debug(f"Scrapling discovered {len(discovered)} URLs to scrape")

        if not discovered:
            self.logger.debug("No URLs discovered, falling back to DDG")
            return self._fallback_duckduckgo_sync(query, max_results)

        # 4. Scrape all discovered URLs in parallel
        results = self._scrape_urls(discovered)

        # 5. If no scrapes succeeded, fallback to DDG snippets
        if not results:
            self.logger.debug("All scrapes failed, falling back to DDG")
            return self._fallback_duckduckgo_sync(query, max_results)

        return results[:max_results]

    # ──────────────────────────────────────────────────────────────
    # Phase 1: Query classification
    # ──────────────────────────────────────────────────────────────

    def _classify_query(self, query: str, explicit_category: Optional[str] = None) -> list[str]:
        """Score query against category keywords to pick top categories."""
        if explicit_category and explicit_category in CATEGORY_KEYWORDS:
            return [explicit_category]

        query_lower = query.lower()
        scores: dict[str, int] = {}

        for cat, keywords in CATEGORY_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw.lower() in query_lower)
            if score > 0:
                scores[cat] = score

        if not scores:
            # Default: broad business categories
            return ["business", "finance", "strategy"]

        # Return top 3 categories
        sorted_cats = sorted(scores, key=scores.get, reverse=True)
        return sorted_cats[:3]

    # ──────────────────────────────────────────────────────────────
    # Phase 2: URL discovery via DuckDuckGo
    # ──────────────────────────────────────────────────────────────

    def _discover_urls(
        self,
        query: str,
        target_sites: dict,
        max_results: int,
    ) -> list[dict]:
        """Use DDG to find URLs on target sites + general results."""
        from ddgs import DDGS

        discovered: list[dict] = []
        seen_urls: set[str] = set()

        ddgs = DDGS()

        # A. Site-specific searches (1 DDG call per site, max_results=2 each)
        for domain in list(target_sites.keys())[:4]:  # Max 4 site: queries
            try:
                site_query = f"site:{domain} {query}"
                raw = list(ddgs.text(site_query, max_results=2))
                for r in raw:
                    url = r.get("href", r.get("link", ""))
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        discovered.append({
                            "title": r.get("title", ""),
                            "url": url,
                            "snippet": r.get("body", r.get("snippet", "")),
                            "domain": domain,
                        })
            except Exception as e:
                self.logger.debug(f"DDG site: search failed for {domain}: {e}")

        # B. General search to fill remaining slots
        remaining = max(max_results - len(discovered), 2)
        try:
            general = list(ddgs.text(query, max_results=remaining))
            for r in general:
                url = r.get("href", r.get("link", ""))
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    # Determine domain
                    from urllib.parse import urlparse
                    parsed_domain = urlparse(url).netloc.replace("www.", "")
                    discovered.append({
                        "title": r.get("title", ""),
                        "url": url,
                        "snippet": r.get("body", r.get("snippet", "")),
                        "domain": parsed_domain,
                    })
        except Exception as e:
            self.logger.debug(f"DDG general search failed: {e}")

        return discovered

    # ──────────────────────────────────────────────────────────────
    # Phase 3: Parallel scraping
    # ──────────────────────────────────────────────────────────────

    def _scrape_urls(self, urls: list[dict]) -> list[dict]:
        """Scrape multiple URLs concurrently using ThreadPoolExecutor."""
        max_workers = min(self.settings.SCRAPLING_MAX_CONCURRENT, len(urls))
        results: list[dict] = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {
                executor.submit(self._scrape_single, item): item
                for item in urls
            }

            for future in as_completed(future_to_url, timeout=self.settings.SCRAPLING_TIMEOUT_SECONDS):
                item = future_to_url[future]
                try:
                    result = future.result(timeout=self.settings.SCRAPLING_TIMEOUT_SECONDS)
                    if result:
                        results.append(result)
                except Exception as e:
                    # Scrape failed — use DDG snippet as fallback for this URL
                    self.logger.debug(f"Scrape failed for {item['url']}: {e}")
                    snippet = item.get("snippet", "")
                    if snippet:
                        results.append({
                            "title": item.get("title", "No title"),
                            "url": item["url"],
                            "content": snippet,
                            "source": "scrapling_fallback",
                        })

        return results

    def _scrape_single(self, item: dict) -> Optional[dict]:
        """
        Scrape a single URL using Scrapling.
        Falls back: page cache → stealthy fetcher → plain fetcher → None.
        """
        url = item["url"]
        domain = item.get("domain", "")
        max_len = self.settings.SCRAPLING_MAX_CONTENT_LENGTH

        # Check page cache first
        cached_content = get_page_cache(url)
        if cached_content:
            return {
                "title": item.get("title", "No title"),
                "url": url,
                "content": cached_content[:max_len],
                "source": "scrapling_cached",
            }

        # Determine site config (if known domain)
        site_config = None
        for reg_domain, config in SITE_REGISTRY.items():
            if reg_domain in domain:
                site_config = config
                break

        # Pick fetcher type
        fetcher_type = site_config.get("fetcher", "plain") if site_config else "plain"
        selectors = site_config.get("selectors", []) if site_config else []

        # Try scraping with the appropriate fetcher
        content = self._fetch_and_extract(url, fetcher_type, selectors)

        # If stealthy failed, retry with plain
        if not content and fetcher_type == "stealthy":
            self.logger.debug(f"Stealthy fetch failed for {url}, retrying with plain")
            content = self._fetch_and_extract(url, "plain", selectors)

        if not content:
            return None

        # Truncate and cache
        content = content[:max_len]
        set_page_cache(url, content)

        return {
            "title": item.get("title", "No title"),
            "url": url,
            "content": content,
            "source": "scrapling",
        }

    def _fetch_and_extract(
        self,
        url: str,
        fetcher_type: str,
        selectors: list[str],
    ) -> Optional[str]:
        """Fetch URL with Scrapling and extract text using CSS selectors."""
        try:
            page = self._fetch_page(url, fetcher_type)
            if page is None:
                return None
            return self._extract_content(page, selectors)
        except Exception as e:
            self.logger.debug(f"Scrapling fetch/extract error for {url}: {e}")
            return None

    def _fetch_page(self, url: str, fetcher_type: str):
        """Fetch a page using Scrapling Fetcher or StealthyFetcher."""
        try:
            if fetcher_type == "stealthy":
                from scrapling.fetchers import StealthyFetcher
                page = StealthyFetcher.fetch(url, headless=True)
            else:
                from scrapling.fetchers import Fetcher
                page = Fetcher.get(url)
            return page
        except Exception as e:
            self.logger.debug(f"Scrapling {fetcher_type} fetch error for {url}: {e}")
            return None

    def _extract_content(self, page, selectors: list[str]) -> Optional[str]:
        """Extract text content from a Scrapling page using CSS selectors."""
        # Try site-specific selectors first
        for selector in selectors:
            try:
                elements = page.css(selector)
                if elements:
                    texts = []
                    for el in elements:
                        text = el.css("::text").get()
                        if text:
                            texts.append(text.strip())
                    content = " ".join(texts).strip()
                    if len(content) > 100:  # Minimum viable content
                        return content
            except Exception:
                continue

        # Try generic fallback selectors
        for selector in GENERIC_SELECTORS:
            try:
                elements = page.css(selector)
                if elements:
                    texts = []
                    for el in elements:
                        text = el.css("::text").get()
                        if text:
                            texts.append(text.strip())
                    content = " ".join(texts).strip()
                    if len(content) > 100:
                        return content
            except Exception:
                continue

        # Last resort: try to get all text from body
        try:
            all_text = page.css("body ::text").getall()
            if all_text:
                content = " ".join(t.strip() for t in all_text if t.strip())
                if len(content) > 100:
                    return content
        except Exception:
            pass

        return None

    # ──────────────────────────────────────────────────────────────
    # Fallback: DuckDuckGo snippets
    # ──────────────────────────────────────────────────────────────

    def _fallback_duckduckgo(self, query: str, max_results: int) -> list[dict]:
        """Async fallback to DDG text search."""
        self.logger.debug("Scrapling falling back to DuckDuckGo snippets")
        return self._fallback_duckduckgo_sync(query, max_results)

    def _fallback_duckduckgo_sync(self, query: str, max_results: int) -> list[dict]:
        """Sync DDG fallback — returns results in standard format."""
        try:
            from ddgs import DDGS
            ddgs = DDGS()
            raw = list(ddgs.text(query, max_results=max_results))
            results = []
            for r in raw:
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", r.get("link", "")),
                    "content": r.get("body", r.get("snippet", "")),
                    "source": "scrapling_ddg_fallback",
                })
            return results
        except Exception as e:
            self.logger.error("Scrapling DDG fallback also failed", e)
            return []


# ──────────────────────────────────────────────────────────────────
# Singleton
# ──────────────────────────────────────────────────────────────────

_engine: Optional[ScraplingEngine] = None


def get_scrapling_engine() -> ScraplingEngine:
    """Get singleton ScraplingEngine instance."""
    global _engine
    if _engine is None:
        _engine = ScraplingEngine()
    return _engine
