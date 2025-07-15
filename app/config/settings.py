from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from typing import Optional


class Settings(BaseSettings):
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True
    )
    
    APP_NAME: str = "Trademk1"
    DEBUG: bool = False
    ENVIRONMENT: str = "production"
    
    DATABASE_URL: Optional[str] = None
    REDIS_URL: Optional[str] = None
    QUESTDB_URL: Optional[str] = None
    
    SECRET_KEY: str = "change-me-in-production"
    
    CORS_ORIGINS: list[str] = ["*"]
    
    # Market data settings
    BINANCE_API_URL: str = "wss://stream.binance.com:9443"
    ALPACA_API_KEY: Optional[str] = None
    ALPACA_API_SECRET: Optional[str] = None
    ALPACA_BASE_URL: str = "https://paper-api.alpaca.markets"


settings = Settings()