"""
Redis-based caching layer for LLM responses and business data.
Provides semantic caching to reduce API costs and improve latency.
"""
import hashlib
import json
from typing import Optional, Any

import redis.asyncio as aioredis

from backend.config import get_settings
from backend.logger import get_logger

logger = get_logger()
_redis_client: Optional[aioredis.Redis] = None


async def init_redis() -> Optional[aioredis.Redis]:
    """Initialize Redis connection pool."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    settings = get_settings()
    logger = get_logger()
    try:
        _redis_client = aioredis.from_url(
            settings.REDIS_URI,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        await _redis_client.ping()
        logger.system("Redis cache connected")
        return _redis_client
    except Exception as e:
        logger.error(f"Redis unavailable - caching disabled", e)
        return None


async def close_redis():
    """Close Redis connection."""
    global _redis_client
    logger = get_logger()
    if _redis_client:
        try:
            await _redis_client.aclose()
        except AttributeError:
            await _redis_client.close()  # Fallback for older redis-py
        _redis_client = None
        logger.system("Redis connection closed")


def _normalize_query(text: str) -> str:
    """Normalize query for consistent cache keys."""
    return text.strip().lower()


def _generate_cache_key(prefix: str, query: str) -> str:
    """Generate a cache key from prefix and normalized query."""
    normalized = _normalize_query(query)
    hash_digest = hashlib.sha256(normalized.encode()).hexdigest()[:16]
    return f"{prefix}:{hash_digest}"


async def get_cached_response(query: str) -> Optional[dict]:
    """
    Retrieve cached LLM response for a query.
    
    Returns:
        Cached response dict with 'content' and metadata, or None if not cached.
    """
    logger = get_logger()
    redis_client = await init_redis()
    if not redis_client:
        return None

    cache_key = _generate_cache_key("llm:response", query)
    try:
        cached = await redis_client.get(cache_key)
        if cached:
            logger.debug(f"Cache HIT for query: {query[:50]}...")
            result = json.loads(cached)
            result["_cache_hit"] = True
            return result
        logger.debug(f"Cache MISS for query: {query[:50]}...")
        return None
    except Exception as e:
        logger.error("Cache read error", e)
        return None


async def set_cached_response(query: str, response: dict, ttl_seconds: int = 3600) -> bool:
    """
    Cache an LLM response.
    
    Args:
        query: The original user query
        response: Response dict to cache (must be JSON-serializable)
        ttl_seconds: Time-to-live in seconds (default 1 hour)
    
    Returns:
        True if cached successfully, False otherwise.
    """
    logger = get_logger()
    redis_client = await init_redis()
    if not redis_client:
        return False

    cache_key = _generate_cache_key("llm:response", query)
    try:
        # Add cache metadata
        cached_data = {
            **response,
            "_cached_at": __import__("time").time(),
            "_ttl_seconds": ttl_seconds,
        }
        await redis_client.setex(cache_key, ttl_seconds, json.dumps(cached_data))
        logger.debug(f"Cached response for query: {query[:50]}... (TTL: {ttl_seconds}s)")
        return True
    except Exception as e:
        logger.error("Cache write error", e)
        return False


async def invalidate_cache(query: str) -> bool:
    """Invalidate cached response for a specific query."""
    logger = get_logger()
    redis_client = await init_redis()
    if not redis_client:
        return False

    cache_key = _generate_cache_key("llm:response", query)
    try:
        await redis_client.delete(cache_key)
        logger.debug(f"Invalidated cache for query: {query[:50]}...")
        return True
    except Exception as e:
        logger.error("Cache invalidation error", e)
        return False


async def clear_all_cache() -> int:
    """Clear all LLM response cache. Returns number of keys cleared."""
    logger = get_logger()
    redis_client = await init_redis()
    if not redis_client:
        return 0

    try:
        keys = await redis_client.keys("llm:response:*")
        if keys:
            deleted = await redis_client.delete(*keys)
            logger.system(f"Cleared {deleted} cached responses")
            return deleted
        return 0
    except Exception as e:
        logger.error("Cache clear error", e)
        return 0


async def get_cache_stats() -> dict:
    """Get cache statistics."""
    logger = get_logger()
    redis_client = await init_redis()
    if not redis_client:
        return {"enabled": False}

    try:
        keys = await redis_client.keys("llm:response:*")
        ttl_values = []
        for key in keys[:100]:  # Sample first 100 keys
            ttl = await redis_client.ttl(key)
            ttl_values.append(ttl)
        
        avg_ttl = sum(ttl_values) / len(ttl_values) if ttl_values else 0
        
        return {
            "enabled": True,
            "total_keys": len(keys),
            "sampled_avg_ttl_seconds": round(avg_ttl, 1),
        }
    except Exception as e:
        logger.error("Cache stats error", e)
        return {"enabled": True, "error": str(e)}


# ---------------------------------------------------------------------------
# Portfolio data caching
# ---------------------------------------------------------------------------

async def cache_portfolio_data(symbol: str, data: dict, ttl_seconds: int = 300) -> bool:
    """Cache portfolio/market data for a symbol."""
    logger = get_logger()
    redis_client = await init_redis()
    if not redis_client:
        return False

    cache_key = f"portfolio:{symbol.upper()}"
    try:
        await redis_client.setex(cache_key, ttl_seconds, json.dumps(data, default=str))
        logger.debug(f"Cached portfolio data for {symbol} (TTL: {ttl_seconds}s)")
        return True
    except Exception as e:
        logger.error("Portfolio cache write error", e)
        return False


async def get_cached_portfolio_data(symbol: str) -> Optional[dict]:
    """Retrieve cached portfolio data for a symbol."""
    logger = get_logger()
    redis_client = await init_redis()
    if not redis_client:
        return None

    cache_key = f"portfolio:{symbol.upper()}"
    try:
        cached = await redis_client.get(cache_key)
        if cached:
            logger.debug(f"Portfolio cache HIT for {symbol}")
            return json.loads(cached)
        return None
    except Exception as e:
        logger.error("Portfolio cache read error", e)
        return None


# ---------------------------------------------------------------------------
# Semantic search caching (for web search results)
# ---------------------------------------------------------------------------

async def cache_web_search(query: str, results: list, ttl_seconds: int = 1800) -> bool:
    """Cache web search results."""
    logger = get_logger()
    redis_client = await init_redis()
    if not redis_client:
        return False

    cache_key = _generate_cache_key("web:search", query)
    try:
        await redis_client.setex(cache_key, ttl_seconds, json.dumps(results, default=str))
        logger.debug(f"Cached web search for: {query[:50]}... (TTL: {ttl_seconds}s)")
        return True
    except Exception as e:
        logger.error("Web search cache error", e)
        return False


async def get_cached_web_search(query: str) -> Optional[list]:
    """Retrieve cached web search results."""
    logger = get_logger()
    redis_client = await init_redis()
    if not redis_client:
        return None

    cache_key = _generate_cache_key("web:search", query)
    try:
        cached = await redis_client.get(cache_key)
        if cached:
            logger.debug(f"Web search cache HIT for: {query[:50]}...")
            return json.loads(cached)
        return None
    except Exception as e:
        logger.error("Web search cache read error", e)
        return None
