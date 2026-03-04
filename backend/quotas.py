"""
User quota and usage tracking system using Redis.
Implements tiered access (Free vs Pro) for business model enablement.
"""
import time
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
import redis.asyncio as aioredis

from backend.cache import init_redis
from backend.auth import get_current_user
from backend.logger import get_logger

# Tier definitions
TIERS = {
    "free": {
        "chat_daily_limit": 50,
        "portfolio_daily_limit": 10,
    },
    "pro": {
        "chat_daily_limit": 500,
        "portfolio_daily_limit": 100,
    }
}

async def get_user_tier(user_id: str, redis_client: aioredis.Redis) -> str:
    """Retrieve the user's tier from Redis, defaulting to 'free'."""
    if user_id == "anonymous":
        return "free"
        
    tier_key = f"user:{user_id}:tier"
    tier = await redis_client.get(tier_key)
    return tier if tier and tier in TIERS else "free"


async def check_quota(user_id: str, feature: str) -> bool:
    """
    Check if the user has enough quota for the requested feature.
    Increments the usage counter if quota is available.
    
    Returns:
        True if allowed, False if quota exceeded.
    """
    logger = get_logger()
    redis_client = await init_redis()
    
    # If Redis is down, fail open (allow request)
    if not redis_client:
        return True
        
    try:
        tier = await get_user_tier(user_id, redis_client)
        limit_key = f"{feature}_daily_limit"
        limit = TIERS.get(tier, TIERS["free"]).get(limit_key, 10)
        
        # Use current date as part of the key for daily resets
        today = time.strftime("%Y-%m-%d")
        usage_key = f"usage:{user_id}:{feature}:{today}"
        
        # Increment usage
        current_usage = await redis_client.incr(usage_key)
        
        # Set expiry for 24 hours on first increment
        if current_usage == 1:
            await redis_client.expire(usage_key, 86400)
            
        logger.debug(f"Quota check for {user_id} ({tier}): {current_usage}/{limit} for {feature}")
        
        return current_usage <= limit
    except Exception as e:
        logger.error(f"Quota check failed", e)
        return True  # Fail open


async def verify_chat_quota(user_id: str = Depends(get_current_user)):
    """Dependency to check chat quota."""
    if not await check_quota(user_id, "chat"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Daily chat quota exceeded. Please upgrade to Pro tier.",
        )
    return user_id


async def verify_portfolio_quota(user_id: str = Depends(get_current_user)):
    """Dependency to check portfolio analysis quota."""
    if not await check_quota(user_id, "portfolio"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Daily portfolio analysis quota exceeded. Please upgrade to Pro tier.",
        )
    return user_id
