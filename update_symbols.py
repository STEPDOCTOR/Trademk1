#!/usr/bin/env python3
"""Update trading symbols - remove WMT and MA, add new tech stocks."""
import asyncio
from uuid import uuid4
from sqlalchemy import select, delete
from app.db.postgres import init_postgres, close_postgres
from app.db.optimized_postgres import optimized_db
from app.models.symbol import Symbol

# Symbols to remove
REMOVE_SYMBOLS = ["WMT", "MA"]

# New symbols to add (tech stocks that complement NVIDIA)
ADD_SYMBOLS = [
    ("AVGO", "Broadcom Inc", "NASDAQ"),  # Semiconductor company
    ("MU", "Micron Technology", "NASDAQ"),  # Memory chips, works with NVIDIA
]

async def update_symbols():
    """Update symbols in database."""
    await init_postgres()
    
    async with optimized_db.get_session() as db:
        # Remove symbols
        for ticker in REMOVE_SYMBOLS:
            result = await db.execute(
                delete(Symbol).where(Symbol.ticker == ticker)
            )
            if result.rowcount > 0:
                print(f"Removed symbol: {ticker}")
            else:
                print(f"Symbol not found: {ticker}")
        
        # Check existing symbols
        result = await db.execute(select(Symbol))
        existing = {s.ticker for s in result.scalars().all()}
        
        # Add new symbols
        for ticker, name, exchange in ADD_SYMBOLS:
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
                print(f"Added stock: {ticker} - {name}")
            else:
                print(f"Symbol already exists: {ticker}")
        
        await db.commit()
        
        # Show current stock symbols
        result = await db.execute(
            select(Symbol).where(Symbol.asset_type == "stock").order_by(Symbol.ticker)
        )
        stocks = result.scalars().all()
        
        print("\nCurrent stock symbols:")
        print("-" * 40)
        for stock in stocks:
            print(f"{stock.ticker:6} - {stock.name}")
        print(f"\nTotal stocks: {len(stocks)}")
    
    await close_postgres()

if __name__ == "__main__":
    asyncio.run(update_symbols())