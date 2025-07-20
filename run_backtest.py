#!/usr/bin/env python3
"""CLI tool for running backtests on aggressive trading strategies."""
import asyncio
import sys
from datetime import datetime, timedelta
import json

from app.services.strategies.aggressive_backtester import AggressiveBacktester


async def main():
    """Run backtest from command line."""
    print("🔄 Aggressive Trading Strategy Backtester")
    print("=" * 50)
    
    # Get strategy preset
    print("\nAvailable strategy presets:")
    print("1. ultra_aggressive - 0.1% momentum, 1.5% stop loss")
    print("2. aggressive - 0.3% momentum, 2% stop loss")
    print("3. balanced - 0.5% momentum, 3% stop loss")
    print("4. conservative - 1% momentum, 5% stop loss")
    
    preset_choice = input("\nSelect preset (1-4) or press Enter for custom: ").strip()
    
    if preset_choice == "1":
        strategy_params = {
            "momentum_threshold": 0.001,
            "min_confidence": 0.4,
            "stop_loss_pct": 0.015,
            "take_profit_pct": 0.03,
            "position_size_pct": 0.03,
            "max_positions": 25
        }
        preset_name = "ultra_aggressive"
    elif preset_choice == "2":
        strategy_params = {
            "momentum_threshold": 0.003,
            "min_confidence": 0.5,
            "stop_loss_pct": 0.02,
            "take_profit_pct": 0.05,
            "position_size_pct": 0.025,
            "max_positions": 20
        }
        preset_name = "aggressive"
    elif preset_choice == "3":
        strategy_params = {
            "momentum_threshold": 0.005,
            "min_confidence": 0.6,
            "stop_loss_pct": 0.03,
            "take_profit_pct": 0.08,
            "position_size_pct": 0.02,
            "max_positions": 15
        }
        preset_name = "balanced"
    elif preset_choice == "4":
        strategy_params = {
            "momentum_threshold": 0.01,
            "min_confidence": 0.7,
            "stop_loss_pct": 0.05,
            "take_profit_pct": 0.15,
            "position_size_pct": 0.015,
            "max_positions": 10
        }
        preset_name = "conservative"
    else:
        # Custom parameters
        preset_name = "custom"
        strategy_params = {
            "momentum_threshold": float(input("Momentum threshold (default 0.003): ") or "0.003"),
            "min_confidence": float(input("Min confidence (default 0.5): ") or "0.5"),
            "stop_loss_pct": float(input("Stop loss % (default 0.02): ") or "0.02"),
            "take_profit_pct": float(input("Take profit % (default 0.05): ") or "0.05"),
            "position_size_pct": float(input("Position size % (default 0.02): ") or "0.02"),
            "max_positions": int(input("Max positions (default 20): ") or "20")
        }
    
    # Add default flags
    strategy_params.update({
        "momentum_enabled": True,
        "technical_entries": True,
        "technical_exits": True,
        "stop_loss_enabled": True,
        "take_profit_enabled": True,
        "trailing_stop_enabled": True,
        "trail_pct": 0.02,
        "dynamic_sizing": True
    })
    
    # Get time period
    days_back = int(input("\nDays to backtest (default 30): ") or "30")
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days_back)
    
    # Get symbols
    symbol_input = input("\nEnter symbols (comma-separated, or press Enter for top movers): ").strip()
    if symbol_input:
        symbols = [s.strip().upper() for s in symbol_input.split(",")]
    else:
        # Default symbols
        symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", 
                  "AMD", "BTCUSD", "ETHUSD", "SPY", "QQQ"]
    
    # Initial capital
    initial_capital = float(input("\nInitial capital (default 100000): ") or "100000")
    
    print(f"\n📊 Running {preset_name} backtest...")
    print(f"Period: {start_date.date()} to {end_date.date()}")
    print(f"Symbols: {', '.join(symbols[:5])}{'...' if len(symbols) > 5 else ''}")
    print(f"Strategy: {strategy_params['momentum_threshold']:.1%} momentum, {strategy_params['stop_loss_pct']:.1%} SL, {strategy_params['take_profit_pct']:.1%} TP")
    print()
    
    # Run backtest
    backtester = AggressiveBacktester(initial_capital=initial_capital)
    
    try:
        results = await backtester.run_backtest(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            strategy_params=strategy_params
        )
        
        # Display results
        print("\n📈 BACKTEST RESULTS")
        print("=" * 50)
        print(f"Total Return: ${results.total_return:,.2f} ({results.total_return_pct:+.2f}%)")
        print(f"Final Capital: ${results.final_capital:,.2f}")
        print()
        print(f"Total Trades: {len(results.trades)}")
        print(f"Winning Trades: {results.winning_trades} ({results.win_rate:.1f}% win rate)")
        print(f"Losing Trades: {results.losing_trades}")
        print(f"Avg Win: ${results.avg_win:,.2f}")
        print(f"Avg Loss: ${results.avg_loss:,.2f}")
        print(f"Profit Factor: {results.profit_factor:.2f}")
        print()
        print(f"Max Drawdown: ${results.max_drawdown:,.2f} ({results.max_drawdown_pct:.2f}%)")
        print(f"Sharpe Ratio: {results.sharpe_ratio:.2f}")
        print(f"Sortino Ratio: {results.sortino_ratio:.2f}")
        print(f"Trades per Day: {results.trades_per_day:.1f}")
        
        if results.best_trade:
            print(f"\nBest Trade: {results.best_trade.symbol} +${results.best_trade.pnl:,.2f} ({results.best_trade.pnl_pct:+.1f}%)")
        if results.worst_trade:
            print(f"Worst Trade: {results.worst_trade.symbol} ${results.worst_trade.pnl:,.2f} ({results.worst_trade.pnl_pct:.1f}%)")
        
        # Save results
        save = input("\n💾 Save detailed results to file? (y/n): ").lower().strip() == 'y'
        if save:
            filename = f"backtest_{preset_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(filename, 'w') as f:
                json.dump(results.to_dict(), f, indent=2, default=str)
            print(f"✅ Results saved to {filename}")
        
    except Exception as e:
        print(f"\n❌ Error running backtest: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    # Run the async main function
    exit_code = asyncio.run(main())
    sys.exit(exit_code)