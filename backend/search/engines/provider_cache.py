"""
Simple provider-level query cache using Redis, patterned after scrapling_cache.py.
Keys: provider:query:{hash}
TTL default falls back to 120s if config missing.
"""
import hashlib
import json
from typing import Optional

from backend.logger import get_logger


def _hash_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _get_redis_client():
    try:
        import redis
        from backend.config import get_settings
        settings = get_settings()
        client = redis.Redis.from_url(settings.REDIS_URI, decode_responses=True)
        client.ping()
        return client
    except Exception:
        return None


def get_cached_provider(query: str, provider: str) -> Optional[dict]:
    logger = get_logger()
    try:
        client = _get_redis_client()
        if client is None:
            return None
        key = f"provider:query:{provider}:{_hash_key(query)}"
        raw = client.get(key)
        if raw:
            logger.debug(f"Provider cache HIT ({provider}): {query[:60]}")
            return json.loads(raw)
        return None
    except Exception as e:
        logger.debug(f"Provider cache read error for {provider}: {e}")
        return None


def set_cached_provider(query: str, provider: str, results: dict, ttl: Optional[int] = None) -> None:
    logger = get_logger()
    try:
        client = _get_redis_client()
        if client is None:
            return
        if ttl is None:
            try:
                from backend.config import get_settings
                ttl = get_settings().PROVIDER_QUERY_CACHE_TTL
            except Exception:
                ttl = 120
        key = f"provider:query:{provider}:{_hash_key(query)}"
        client.setex(key, ttl, json.dumps(results))
        logger.debug(f"Provider cache SET ({provider}): {query[:60]}, TTL={ttl}s")
    except Exception as e:
        logger.debug(f"Provider cache write error for {provider}: {e}")
