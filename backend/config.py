"""
Configuration management for AI Business Advisor.
Uses Pydantic Settings for environment variable handling.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # API Keys
    NVIDIA_API_KEY: str = ""
    TAVILY_API_KEY: str = ""
    SONAR_API_KEY: str = ""
    FINNHUB_API_KEY: str = ""
    
    # Model Configuration
    MODEL_NAME: str = "nvidia/llama-3.3-nemotron-super-49b-v1.5"
    MODEL_TEMPERATURE: float = 0.6  # Balanced creativity for reasoning model
    MODEL_MAX_TOKENS: int = 8192    # Reduced for faster inference (was 65536)
    MODEL_TOP_P: float = 0.95       # Nucleus sampling
    MODEL_FREQUENCY_PENALTY: float = 0  # No frequency penalty
    MODEL_PRESENCE_PENALTY: float = 0   # No presence penalty
    
    # Application Settings
    APP_NAME: str = "AI Business Advisor"
    APP_VERSION: str = "1.0.0-mvp"
    DEBUG: bool = False
    
    # Logging Settings
    LOG_LEVEL: str = "DEBUG"  # DEBUG, INFO, WARNING, ERROR
    
    # Server Configuration
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # CORS Settings (for frontend)
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:5500", "http://127.0.0.1:5500"]

    # Database & Cache
    POSTGRES_URI: str = "postgresql://advisor:advisor_password@localhost:5432/ai_advisor"
    REDIS_URI: str = "redis://localhost:6379/0"
    
    # Graph Database
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "advisor_password"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
