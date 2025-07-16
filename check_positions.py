#!/usr/bin/env python3
"""Check existing Alpaca positions"""
import asyncio
import os
from alpaca.trading.client import TradingClient
from dotenv import load_dotenv

async def main():
    load_dotenv()
    
    # Initialize trading client
    trading_client = TradingClient(
        api_key=os.getenv("ALPACA_API_KEY"),
        secret_key=os.getenv("ALPACA_API_SECRET"),
        paper=True
    )
    
    # Get account info
    account = trading_client.get_account()
    print(f"Account Status: {account.status}")
    print(f"Buying Power: ${float(account.buying_power):,.2f}")
    print(f"Portfolio Value: ${float(account.portfolio_value):,.2f}")
    print(f"Cash: ${float(account.cash):,.2f}")
    print()
    
    # Get all positions
    positions = trading_client.get_all_positions()
    
    if positions:
        print("Current Positions:")
        print("-" * 80)
        for pos in positions:
            pnl_pct = (float(pos.unrealized_plpc) * 100) if pos.unrealized_plpc else 0
            print(f"Symbol: {pos.symbol}")
            print(f"  Qty: {pos.qty}")
            print(f"  Avg Cost: ${float(pos.avg_entry_price):,.2f}")
            print(f"  Current Price: ${float(pos.current_price):,.2f}")
            print(f"  Market Value: ${float(pos.market_value):,.2f}")
            print(f"  Unrealized P&L: ${float(pos.unrealized_pl):,.2f} ({pnl_pct:+.2f}%)")
            print(f"  Asset Class: {pos.asset_class}")
            print()
    else:
        print("No open positions found.")
    
    # Get recent orders
    orders = trading_client.get_orders(status="all", limit=10)
    if orders:
        print("\nRecent Orders:")
        print("-" * 80)
        for order in orders[:5]:
            print(f"{order.symbol} - {order.side} {order.qty} @ {order.order_type} - Status: {order.status}")
            if order.filled_at:
                print(f"  Filled at: ${float(order.filled_avg_price):,.2f}")
    
    # Get asset list to see what's tradeable
    assets = trading_client.get_all_assets(status="active", asset_class="us_equity")
    tradeable_stocks = [a for a in assets if a.tradable][:10]
    print(f"\nTradeable US Stocks: {len([a for a in assets if a.tradable])} available")
    print("Sample:", [a.symbol for a in tradeable_stocks])
    
    crypto_assets = trading_client.get_all_assets(status="active", asset_class="crypto")
    tradeable_crypto = [a for a in crypto_assets if a.tradable][:10]
    print(f"\nTradeable Crypto: {len([a for a in crypto_assets if a.tradable])} available")
    print("Sample:", [a.symbol for a in tradeable_crypto])

if __name__ == "__main__":
    asyncio.run(main())