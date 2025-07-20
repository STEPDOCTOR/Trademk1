#!/usr/bin/env python3
"""Check trading performance and display dashboard."""
import requests
import json
from datetime import datetime
from typing import Dict, Any

def format_money(value: float) -> str:
    """Format money values with color."""
    if value > 0:
        return f"\033[92m+${value:,.2f}\033[0m"  # Green
    elif value < 0:
        return f"\033[91m-${abs(value):,.2f}\033[0m"  # Red
    else:
        return f"${value:,.2f}"

def format_pct(value: float) -> str:
    """Format percentage values with color."""
    if value > 0:
        return f"\033[92m+{value:.2f}%\033[0m"  # Green
    elif value < 0:
        return f"\033[91m{value:.2f}%\033[0m"  # Red
    else:
        return f"{value:.2f}%"

def print_dashboard():
    """Print performance dashboard."""
    print("\n" + "="*60)
    print("🎯 AGGRESSIVE BOT PERFORMANCE DASHBOARD")
    print("="*60)
    
    try:
        # Get realtime metrics
        response = requests.get("http://localhost:8000/api/v1/performance/realtime")
        if response.status_code == 200:
            metrics = response.json()
            
            print("\n📊 REAL-TIME METRICS")
            print("-"*40)
            print(f"Session Start: {metrics.get('session_start', 'N/A')}")
            print(f"Last Updated: {metrics.get('last_updated', 'N/A')}")
            print()
            
            # P&L Section
            print("💰 PROFIT & LOSS")
            print(f"  Unrealized P&L: {format_money(metrics.get('unrealized_pnl', 0))}")
            print(f"  Realized P&L: {format_money(metrics.get('realized_pnl', 0))}")
            print(f"  Total P&L: {format_money(metrics.get('total_pnl', 0))} ({format_pct(metrics.get('total_pnl_pct', 0))})")
            print()
            
            # Position Section
            print("📈 POSITIONS")
            print(f"  Open Positions: {metrics.get('open_positions', 0)}")
            print(f"  Position Value: ${metrics.get('total_position_value', 0):,.2f}")
            print(f"  Cash Available: ${metrics.get('cash_available', 0):,.2f}")
            print(f"  Buying Power: ${metrics.get('buying_power', 0):,.2f}")
            print()
            
            # Today's Activity
            print("📅 TODAY'S ACTIVITY")
            trades_today = metrics.get('trades_today', 0)
            wins_today = metrics.get('winning_trades_today', 0)
            losses_today = metrics.get('losing_trades_today', 0)
            win_rate = (wins_today / trades_today * 100) if trades_today > 0 else 0
            
            print(f"  Trades: {trades_today} (Wins: {wins_today}, Losses: {losses_today})")
            print(f"  Win Rate: {format_pct(win_rate)}")
            print(f"  Volume: ${metrics.get('volume_today', 0):,.2f}")
            print()
            
            # Limit Status
            if 'limit_status' in metrics:
                limit = metrics['limit_status']
                print("⚠️  DAILY LIMITS")
                if limit.get('loss_limit_hit'):
                    print(f"  ❌ LOSS LIMIT HIT! ({format_money(limit['current_pnl'])})")
                else:
                    print(f"  Loss Progress: {limit.get('pct_to_loss_limit', 0):.1f}% of limit")
                
                if limit.get('profit_target_hit'):
                    print(f"  ✅ PROFIT TARGET HIT! ({format_money(limit['current_pnl'])})")
                else:
                    print(f"  Profit Progress: {limit.get('pct_to_profit_target', 0):.1f}% of target")
        
        # Get recent trades
        print("\n💱 RECENT TRADES")
        print("-"*40)
        response = requests.get("http://localhost:8000/api/v1/performance/trades/recent?limit=5")
        if response.status_code == 200:
            trades = response.json()
            for trade in trades:
                symbol = trade['symbol']
                trade_type = trade['type'].upper()
                qty = trade['quantity']
                price = trade['price']
                pnl = trade.get('profit_loss')
                reason = trade['reason']
                
                trade_str = f"{trade_type} {qty} {symbol} @ ${price:.2f} ({reason})"
                if pnl:
                    trade_str += f" P&L: {format_money(pnl)}"
                print(f"  {trade_str}")
        
        # Get alerts
        print("\n🚨 ALERTS")
        print("-"*40)
        response = requests.get("http://localhost:8000/api/v1/performance/alerts")
        if response.status_code == 200:
            alerts = response.json()
            if alerts:
                for alert in alerts:
                    level = alert['level'].upper()
                    message = alert['message']
                    action = alert.get('action', '')
                    
                    if level == "CRITICAL":
                        print(f"  ❌ {message}")
                    elif level == "WARNING":
                        print(f"  ⚠️  {message}")
                    elif level == "SUCCESS":
                        print(f"  ✅ {message}")
                    else:
                        print(f"  ℹ️  {message}")
                    
                    if action:
                        print(f"     → {action}")
            else:
                print("  ✅ No alerts")
        
        # Get summary
        print("\n📈 30-DAY SUMMARY")
        print("-"*40)
        response = requests.get("http://localhost:8000/api/v1/performance/summary?days=30")
        if response.status_code == 200:
            summary = response.json()
            if summary.get('total_trades', 0) > 0:
                print(f"  Trading Days: {summary['trading_days']}")
                print(f"  Total Trades: {summary['total_trades']}")
                print(f"  Total P&L: {format_money(summary['total_pnl'])}")
                print(f"  Average Daily P&L: {format_money(summary['average_daily_pnl'])}")
                print(f"  Win Rate: {format_pct(summary['win_rate'])}")
                print(f"  Best Day: {format_money(summary['best_day'])}")
                print(f"  Worst Day: {format_money(summary['worst_day'])}")
                print(f"  Sharpe Ratio: {summary['sharpe_ratio']}")
                
                if summary.get('pnl_by_strategy'):
                    print("\n  P&L by Strategy:")
                    for strategy, pnl in summary['pnl_by_strategy'].items():
                        print(f"    {strategy}: {format_money(pnl)}")
            else:
                print("  No trading data for this period")
                
    except requests.exceptions.ConnectionError:
        print("\n❌ Error: Cannot connect to API. Make sure the app is running.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
    
    print("\n" + "="*60)
    print(f"Last checked: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60 + "\n")

if __name__ == "__main__":
    print_dashboard()