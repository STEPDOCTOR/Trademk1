#!/usr/bin/env python3
"""Populate symbols table with trading symbols."""
import asyncio
from uuid import uuid4
from sqlalchemy import select
from app.db.postgres import init_postgres, close_postgres
from app.db.optimized_postgres import optimized_db
from app.models.symbol import Symbol

# Your existing positions
STOCK_SYMBOLS = [
    ("AMD", "Advanced Micro Devices", "NASDAQ"),
    ("AMZN", "Amazon.com Inc", "NASDAQ"),
    ("GOOGL", "Alphabet Inc Class A", "NASDAQ"),
    ("HD", "Home Depot Inc", "NYSE"),
    ("INTC", "Intel Corporation", "NASDAQ"),
    ("JNJ", "Johnson & Johnson", "NYSE"),
    ("META", "Meta Platforms Inc", "NASDAQ"),
    ("NIO", "NIO Inc", "NYSE"),
    ("NVDA", "NVIDIA Corporation", "NASDAQ"),
    ("PYPL", "PayPal Holdings Inc", "NASDAQ"),
    ("SOFI", "SoFi Technologies Inc", "NASDAQ"),
    ("SPY", "SPDR S&P 500 ETF", "NYSE"),
    ("T", "AT&T Inc", "NYSE"),
    ("V", "Visa Inc", "NYSE"),
    # Add some popular stocks for momentum trading
    ("AAPL", "Apple Inc", "NASDAQ"),
    ("MSFT", "Microsoft Corporation", "NASDAQ"),
    ("TSLA", "Tesla Inc", "NASDAQ"),
    ("JPM", "JPMorgan Chase & Co", "NYSE"),
    ("AVGO", "Broadcom Inc", "NASDAQ"),  # Semiconductor company
    ("MU", "Micron Technology", "NASDAQ"),  # Memory chips, works with NVIDIA
]

CRYPTO_SYMBOLS = [
    ("BTCUSD", "Bitcoin", "CRYPTO"),
    ("ETHUSD", "Ethereum", "CRYPTO"),
    ("SOLUSD", "Solana", "CRYPTO"),
    ("ADAUSD", "Cardano", "CRYPTO"),
    ("DOGEUSD", "Dogecoin", "CRYPTO"),
    ("MATICUSD", "Polygon", "CRYPTO"),
    ("LINKUSD", "Chainlink", "CRYPTO"),
    ("DOTUSD", "Polkadot", "CRYPTO"),
    ("UNIUSD", "Uniswap", "CRYPTO"),
    ("LTCUSD", "Litecoin", "CRYPTO"),
]

async def populate_symbols():
    """Populate symbols in database."""
    await init_postgres()
    
    async with optimized_db.get_session() as db:
        # Check existing symbols
        result = await db.execute(select(Symbol))
        existing = {s.ticker for s in result.scalars().all()}
        
        # Add stocks
        for ticker, name, exchange in STOCK_SYMBOLS:
            if ticker not in existing:
                symbol = Symbol(
                    id=uuid4(),
                    ticker=ticker,
                    name=name,
                    exchange=exchange,
                    asset_type="stock",
                    is_active=True
                )
                db.add(symbol)
                print(f"Added stock: {ticker}")
        
        # Add crypto
        for ticker, name, exchange in CRYPTO_SYMBOLS:
            if ticker not in existing:
                symbol = Symbol(
                    id=uuid4(),
                    ticker=ticker,
                    name=name,
                    exchange=exchange,
                    asset_type="crypto",
                    is_active=True
                )
                db.add(symbol)
                print(f"Added crypto: {ticker}")
        
        await db.commit()
        print("Symbols populated successfully")
    
    await close_postgres()

if __name__ == "__main__":
    asyncio.run(populate_symbols())