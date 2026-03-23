# Search Engines Module
from backend.search.engines.duckduckgo import get_duckduckgo_engine, DuckDuckGoEngine
from backend.search.engines.scrapling_engine import get_scrapling_engine, ScraplingEngine

__all__ = [
    "get_duckduckgo_engine",
    "DuckDuckGoEngine",
    "get_scrapling_engine",
    "ScraplingEngine",
]
