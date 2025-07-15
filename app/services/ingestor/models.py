"""Data models for market data ingestion."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class Exchange(str, Enum):
    """Supported exchanges."""
    BINANCE = "BINANCE"
    ALPACA = "ALPACA"


class TickType(str, Enum):
    """Types of market ticks."""
    QUOTE = "QUOTE"
    TRADE = "TRADE"
    BAR = "BAR"


@dataclass
class Tick:
    """Unified market tick data."""
    symbol: str
    exchange: Exchange
    tick_type: TickType
    timestamp: datetime
    price: float
    bid_price: Optional[float] = None
    ask_price: Optional[float] = None
    bid_size: Optional[float] = None
    ask_size: Optional[float] = None
    volume: Optional[float] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for database insertion."""
        return {
            "symbol": self.symbol,
            "exchange": self.exchange.value,
            "price": self.price,
            "bid_price": self.bid_price,
            "ask_price": self.ask_price,
            "bid_size": self.bid_size,
            "ask_size": self.ask_size,
            "volume": self.volume,
            "timestamp": self.timestamp,
        }


# Top 15 cryptocurrencies by market cap (as of 2024)
TOP_15_CRYPTOS = [
    "BTCUSDT",   # Bitcoin
    "ETHUSDT",   # Ethereum
    "BNBUSDT",   # Binance Coin
    "SOLUSDT",   # Solana
    "XRPUSDT",   # Ripple
    "USDCUSDT",  # USD Coin
    "ADAUSDT",   # Cardano
    "AVAXUSDT",  # Avalanche
    "DOGEUSDT",  # Dogecoin
    "TRXUSDT",   # TRON
    "DOTUSDT",   # Polkadot
    "LINKUSDT",  # Chainlink
    "MATICUSDT", # Polygon
    "SHIBUSDT",  # Shiba Inu
    "LTCUSDT",   # Litecoin
]

# Popular US stocks for trading
US_STOCKS = [
    "AAPL",   # Apple
    "MSFT",   # Microsoft
    "GOOGL",  # Alphabet
    "AMZN",   # Amazon
    "NVDA",   # NVIDIA
    "TSLA",   # Tesla
    "META",   # Meta
    "BRK.B",  # Berkshire Hathaway
    "JPM",    # JPMorgan Chase
    "V",      # Visa
    "JNJ",    # Johnson & Johnson
    "WMT",    # Walmart
    "PG",     # Procter & Gamble
    "MA",     # Mastercard
    "UNH",    # UnitedHealth
]