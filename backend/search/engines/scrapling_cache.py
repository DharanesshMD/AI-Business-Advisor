"""
Two-tier Redis cache for Scrapling deep scraping.

  - Query-level:  scrape:query:{hash}  → 30 min TTL  (repeat queries instant)
  - Page-level:   scrape:page:{hash}   → 2 hr TTL    (avoid re-scraping same URLs)

Falls back gracefully when Redis is unavailable — scraping still works, just uncached.
"""

import hashlib
import json
from typing import Optional

from backend.logger import get_logger


def _hash_key(text: str) -> str:
    """Create a short deterministic hash for cache keys."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _get_redis_client():
    """Get Redis client; returns None if unavailable."""
    try:
        import redis
        from backend.config import get_settings
        settings = get_settings()
        client = redis.Redis.from_url(settings.REDIS_URI, decode_responses=True)
        client.ping()  # Verify connection
        return client
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────
# Query-level cache  (input: query string → output: list[dict])
# ──────────────────────────────────────────────────────────────────

def get_query_cache(query: str) -> Optional[list[dict]]:
    """Return cached results for a query, or None on miss/error."""
    logger = get_logger()
    try:
        client = _get_redis_client()
        if client is None:
            return None
        key = f"scrape:query:{_hash_key(query)}"
        raw = client.get(key)
        if raw:
            logger.debug(f"Scrapling cache HIT (query): {query[:60]}")
            return json.loads(raw)
        return None
    except Exception as e:
        logger.debug(f"Scrapling query cache read error: {e}")
        return None


def set_query_cache(query: str, results: list[dict], ttl: Optional[int] = None) -> None:
    """Store query results in cache."""
    logger = get_logger()
    try:
        client = _get_redis_client()
        if client is None:
            return
        if ttl is None:
            from backend.config import get_settings
            ttl = get_settings().SCRAPLING_QUERY_CACHE_TTL
        key = f"scrape:query:{_hash_key(query)}"
        client.setex(key, ttl, json.dumps(results))
        logger.debug(f"Scrapling cache SET (query): {query[:60]}, TTL={ttl}s")
    except Exception as e:
        logger.debug(f"Scrapling query cache write error: {e}")


# ──────────────────────────────────────────────────────────────────
# Page-level cache  (input: URL → output: scraped content string)
# ──────────────────────────────────────────────────────────────────

def get_page_cache(url: str) -> Optional[str]:
    """Return cached page content for a URL, or None on miss/error."""
    logger = get_logger()
    try:
        client = _get_redis_client()
        if client is None:
            return None
        key = f"scrape:page:{_hash_key(url)}"
        raw = client.get(key)
        if raw:
            logger.debug(f"Scrapling cache HIT (page): {url[:80]}")
            return raw
        return None
    except Exception as e:
        logger.debug(f"Scrapling page cache read error: {e}")
        return None


def set_page_cache(url: str, content: str, ttl: Optional[int] = None) -> None:
    """Store scraped page content in cache."""
    logger = get_logger()
    try:
        client = _get_redis_client()
        if client is None:
            return
        if ttl is None:
            from backend.config import get_settings
            ttl = get_settings().SCRAPLING_CACHE_TTL
        key = f"scrape:page:{_hash_key(url)}"
        client.setex(key, ttl, content)
        logger.debug(f"Scrapling cache SET (page): {url[:80]}, TTL={ttl}s")
    except Exception as e:
        logger.debug(f"Scrapling page cache write error: {e}")
