#!/usr/bin/env python3
"""Interactive control panel for Trademk1 trading bot."""
import asyncio
import aiohttp
import json
import os
import sys
from datetime import datetime
from typing import Dict, Any, Optional

# ANSI color codes for better UI
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

API_URL = "http://localhost:8000"
TOKEN_FILE = ".control_panel_token"


class TradingBotControlPanel:
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.token: Optional[str] = None
        self.headers: Dict[str, str] = {}
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        await self.login()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            
    async def login(self):
        """Login and store token."""
        # Check for saved token
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, 'r') as f:
                self.token = f.read().strip()
                self.headers = {"Authorization": f"Bearer {self.token}"}
                
            # Verify token is still valid
            async with self.session.get(f"{API_URL}/api/v1/auth/me", headers=self.headers) as resp:
                if resp.status == 200:
                    user = await resp.json()
                    print(f"{Colors.GREEN}✓ Logged in as: {user['email']}{Colors.ENDC}")
                    return
                    
        # Need to login
        print(f"{Colors.YELLOW}Please login to continue:{Colors.ENDC}")
        email = input("Email: ")
        password = input("Password: ")
        
        login_data = {"username": email, "password": password}
        
        async with self.session.post(f"{API_URL}/api/v1/auth/login", data=login_data) as resp:
            if resp.status != 200:
                print(f"{Colors.RED}✗ Login failed!{Colors.ENDC}")
                sys.exit(1)
                
            result = await resp.json()
            self.token = result["access_token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}
            
            # Save token
            with open(TOKEN_FILE, 'w') as f:
                f.write(self.token)
                
            print(f"{Colors.GREEN}✓ Login successful!{Colors.ENDC}")
            
    def clear_screen(self):
        """Clear the terminal screen."""
        os.system('clear' if os.name == 'posix' else 'cls')
        
    def print_header(self):
        """Print the header."""
        self.clear_screen()
        print(f"{Colors.HEADER}{Colors.BOLD}")
        print("╔════════════════════════════════════════════════════════════════╗")
        print("║              TRADEMK1 TRADING BOT CONTROL PANEL                ║")
        print("╚════════════════════════════════════════════════════════════════╝")
        print(f"{Colors.ENDC}")
        
    async def show_main_menu(self):
        """Show main menu and get user choice."""
        self.print_header()
        
        # Get current status
        status = await self.get_bot_status()
        autonomous_running = status.get('autonomous_running', False)
        
        print(f"{Colors.CYAN}Current Status:{Colors.ENDC}")
        print(f"  Autonomous Trading: {Colors.GREEN if autonomous_running else Colors.RED}{'Running' if autonomous_running else 'Stopped'}{Colors.ENDC}")
        print(f"  Active Positions: {status.get('position_count', 0)}")
        print(f"  Today's P&L: ${status.get('daily_pnl', 0):.2f}")
        print()
        
        print(f"{Colors.BOLD}Main Menu:{Colors.ENDC}")
        print("1. 🤖 Autonomous Trading Control")
        print("2. 📊 Trading Strategies")
        print("3. 🌐 Exchange Management")
        print("4. 🧠 Machine Learning")
        print("5. 📈 Market Analysis")
        print("6. 💼 Portfolio Management")
        print("7. ⚙️  Advanced Features")
        print("8. 📊 View Dashboard")
        print("9. 🔧 System Settings")
        print("0. 🚪 Exit")
        print()
        
        choice = input(f"{Colors.YELLOW}Enter your choice (0-9): {Colors.ENDC}")
        return choice
        
    async def get_bot_status(self) -> Dict[str, Any]:
        """Get current bot status."""
        status = {}
        
        # Get autonomous status
        async with self.session.get(f"{API_URL}/api/v1/autonomous/status", headers=self.headers) as resp:
            if resp.status == 200:
                result = await resp.json()
                status['autonomous_running'] = result['running']
                
        # Get positions
        async with self.session.get(f"{API_URL}/api/v1/trading/positions", headers=self.headers) as resp:
            if resp.status == 200:
                result = await resp.json()
                status['position_count'] = len(result.get('positions', []))
                
        # Get daily P&L
        async with self.session.get(f"{API_URL}/api/v1/performance/daily", headers=self.headers) as resp:
            if resp.status == 200:
                result = await resp.json()
                status['daily_pnl'] = result.get('total_pnl', 0)
                
        return status
        
    async def autonomous_trading_menu(self):
        """Autonomous trading control menu."""
        while True:
            self.print_header()
            print(f"{Colors.BOLD}Autonomous Trading Control{Colors.ENDC}")
            print()
            
            # Get current status
            async with self.session.get(f"{API_URL}/api/v1/autonomous/status", headers=self.headers) as resp:
                if resp.status == 200:
                    status = await resp.json()
                    running = status['running']
                    
                    print(f"Status: {Colors.GREEN if running else Colors.RED}{'Running' if running else 'Stopped'}{Colors.ENDC}")
                    print()
                    
                    # Show enabled strategies
                    print("Enabled Strategies:")
                    for strategy, config in status['strategies'].items():
                        if config['enabled']:
                            print(f"  ✓ {strategy}")
                    print()
            
            print("1. ▶️  Start Autonomous Trading")
            print("2. ⏸️  Stop Autonomous Trading")
            print("3. ⚡ Enable Aggressive Mode")
            print("4. 🛡️  Enable Conservative Mode")
            print("5. 🎯 Configure Individual Strategies")
            print("6. 🔄 Force Trading Cycle")
            print("7. 📊 View Performance")
            print("0. ⬅️  Back to Main Menu")
            print()
            
            choice = input(f"{Colors.YELLOW}Enter your choice: {Colors.ENDC}")
            
            if choice == '0':
                break
            elif choice == '1':
                await self.start_autonomous_trading()
            elif choice == '2':
                await self.stop_autonomous_trading()
            elif choice == '3':
                await self.enable_aggressive_mode()
            elif choice == '4':
                await self.enable_conservative_mode()
            elif choice == '5':
                await self.configure_strategies()
            elif choice == '6':
                await self.force_trading_cycle()
            elif choice == '7':
                await self.view_performance()
                
            if choice != '0':
                input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.ENDC}")
                
    async def start_autonomous_trading(self):
        """Start autonomous trading."""
        async with self.session.post(f"{API_URL}/api/v1/autonomous/start", headers=self.headers) as resp:
            if resp.status == 200:
                print(f"{Colors.GREEN}✓ Autonomous trading started!{Colors.ENDC}")
            else:
                print(f"{Colors.RED}✗ Failed to start autonomous trading{Colors.ENDC}")
                
    async def stop_autonomous_trading(self):
        """Stop autonomous trading."""
        async with self.session.post(f"{API_URL}/api/v1/autonomous/stop", headers=self.headers) as resp:
            if resp.status == 200:
                print(f"{Colors.GREEN}✓ Autonomous trading stopped!{Colors.ENDC}")
            else:
                print(f"{Colors.RED}✗ Failed to stop autonomous trading{Colors.ENDC}")
                
    async def enable_aggressive_mode(self):
        """Enable aggressive trading mode."""
        print(f"{Colors.YELLOW}Enabling aggressive mode...{Colors.ENDC}")
        
        strategies = {
            "momentum": {"enabled": True, "momentum_threshold": 0.001, "max_positions": 30},
            "stop_loss": {"enabled": True, "stop_loss_pct": 0.02},
            "take_profit": {"enabled": True, "take_profit_pct": 0.05},
            "technical_analysis": {"enabled": True, "min_confidence": 0.5},
            "ml_prediction": {"enabled": True, "min_confidence": 0.65, "min_return": 0.002}
        }
        
        for strategy, config in strategies.items():
            async with self.session.patch(
                f"{API_URL}/api/v1/autonomous/strategy/{strategy}",
                headers=self.headers,
                json=config
            ) as resp:
                if resp.status == 200:
                    print(f"  ✓ {strategy} configured")
                    
        print(f"{Colors.GREEN}✓ Aggressive mode enabled!{Colors.ENDC}")
        
    async def enable_conservative_mode(self):
        """Enable conservative trading mode."""
        print(f"{Colors.YELLOW}Enabling conservative mode...{Colors.ENDC}")
        
        strategies = {
            "momentum": {"enabled": True, "momentum_threshold": 0.03, "max_positions": 10},
            "stop_loss": {"enabled": True, "stop_loss_pct": 0.05},
            "take_profit": {"enabled": True, "take_profit_pct": 0.15},
            "technical_analysis": {"enabled": True, "min_confidence": 0.7},
            "ml_prediction": {"enabled": False}
        }
        
        for strategy, config in strategies.items():
            async with self.session.patch(
                f"{API_URL}/api/v1/autonomous/strategy/{strategy}",
                headers=self.headers,
                json=config
            ) as resp:
                if resp.status == 200:
                    print(f"  ✓ {strategy} configured")
                    
        print(f"{Colors.GREEN}✓ Conservative mode enabled!{Colors.ENDC}")
        
    async def configure_strategies(self):
        """Configure individual strategies."""
        # This would show a submenu for configuring each strategy
        print(f"{Colors.CYAN}Strategy configuration coming soon...{Colors.ENDC}")
        
    async def force_trading_cycle(self):
        """Force an immediate trading cycle."""
        async with self.session.post(f"{API_URL}/api/v1/autonomous/force-cycle", headers=self.headers) as resp:
            if resp.status == 200:
                result = await resp.json()
                print(f"{Colors.GREEN}✓ Trading cycle executed!{Colors.ENDC}")
                print(f"Signals generated: {result.get('signals_count', 0)}")
            else:
                print(f"{Colors.RED}✗ Failed to execute trading cycle{Colors.ENDC}")
                
    async def view_performance(self):
        """View trading performance."""
        async with self.session.get(f"{API_URL}/api/v1/performance/summary", headers=self.headers) as resp:
            if resp.status == 200:
                perf = await resp.json()
                print(f"\n{Colors.BOLD}Performance Summary:{Colors.ENDC}")
                print(f"  Total P&L: ${perf.get('total_pnl', 0):.2f}")
                print(f"  Win Rate: {perf.get('win_rate', 0):.1%}")
                print(f"  Total Trades: {perf.get('total_trades', 0)}")
                print(f"  Sharpe Ratio: {perf.get('sharpe_ratio', 0):.2f}")
                
    async def trading_strategies_menu(self):
        """Trading strategies menu."""
        while True:
            self.print_header()
            print(f"{Colors.BOLD}Trading Strategies{Colors.ENDC}")
            print()
            
            print("1. 🔄 Pairs Trading")
            print("2. 📊 Options Strategies")
            print("3. 💹 Market Making")
            print("4. 🔍 Arbitrage Scanner")
            print("5. 📈 Mean Reversion")
            print("6. 🚀 Breakout Detection")
            print("7. 📊 Volume-Weighted Strategies")
            print("0. ⬅️  Back to Main Menu")
            print()
            
            choice = input(f"{Colors.YELLOW}Enter your choice: {Colors.ENDC}")
            
            if choice == '0':
                break
            elif choice == '1':
                await self.pairs_trading_menu()
            elif choice == '2':
                await self.options_strategies_menu()
            elif choice == '3':
                await self.market_making_menu()
            elif choice == '4':
                await self.arbitrage_scanner_menu()
            else:
                print(f"{Colors.CYAN}Feature coming soon...{Colors.ENDC}")
                
            if choice != '0':
                input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.ENDC}")
                
    async def pairs_trading_menu(self):
        """Pairs trading control."""
        print(f"\n{Colors.BOLD}Pairs Trading{Colors.ENDC}")
        
        # Find cointegrated pairs
        symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "META"]
        print(f"Scanning for cointegrated pairs among: {', '.join(symbols)}")
        
        # This would call the pairs trading API
        print(f"{Colors.CYAN}Pairs trading analysis in progress...{Colors.ENDC}")
        
    async def options_strategies_menu(self):
        """Options strategies menu."""
        print(f"\n{Colors.BOLD}Options Strategies{Colors.ENDC}")
        print("1. Covered Calls")
        print("2. Cash-Secured Puts")
        print("3. Vertical Spreads")
        print("4. Iron Condors")
        
        # This would show options strategies
        print(f"{Colors.CYAN}Options trading integration coming soon...{Colors.ENDC}")
        
    async def market_making_menu(self):
        """Market making control."""
        print(f"\n{Colors.BOLD}Market Making{Colors.ENDC}")
        
        symbol = input("Enter symbol for market making: ").upper()
        spread_bps = input("Enter spread in basis points (default 10): ") or "10"
        
        print(f"{Colors.CYAN}Market making setup for {symbol} with {spread_bps}bps spread...{Colors.ENDC}")
        
    async def arbitrage_scanner_menu(self):
        """Arbitrage scanner control."""
        print(f"\n{Colors.BOLD}Arbitrage Scanner{Colors.ENDC}")
        
        symbols = ["BTCUSD", "ETHUSD", "LTCUSD"]
        
        async with self.session.post(
            f"{API_URL}/api/v1/exchanges/arbitrage/scan",
            headers=self.headers,
            json={"symbols": symbols, "min_profit_pct": 0.001}
        ) as resp:
            if resp.status == 200:
                result = await resp.json()
                opportunities = result.get('opportunities', [])
                
                if opportunities:
                    print(f"\n{Colors.GREEN}Found {len(opportunities)} arbitrage opportunities:{Colors.ENDC}")
                    for opp in opportunities[:5]:
                        print(f"  {opp['symbols'][0]}: {opp['spread_pct']:.2%} spread between {opp['exchanges'][0]} and {opp['exchanges'][1]}")
                else:
                    print(f"{Colors.YELLOW}No arbitrage opportunities found{Colors.ENDC}")
                    
    async def exchange_management_menu(self):
        """Exchange management menu."""
        while True:
            self.print_header()
            print(f"{Colors.BOLD}Exchange Management{Colors.ENDC}")
            print()
            
            # Get exchange status
            async with self.session.get(f"{API_URL}/api/v1/exchanges/status", headers=self.headers) as resp:
                if resp.status == 200:
                    status = await resp.json()
                    
                    print("Exchange Status:")
                    for exchange, info in status['exchanges'].items():
                        status_color = Colors.GREEN if info['enabled'] else Colors.RED
                        print(f"  {exchange}: {status_color}{'Enabled' if info['enabled'] else 'Disabled'}{Colors.ENDC}")
                    print()
            
            print("1. 🟢 Enable Exchange")
            print("2. 🔴 Disable Exchange")
            print("3. 💱 View Exchange Quotes")
            print("4. 💰 View Balances")
            print("5. 🔍 Scan Arbitrage")
            print("0. ⬅️  Back to Main Menu")
            print()
            
            choice = input(f"{Colors.YELLOW}Enter your choice: {Colors.ENDC}")
            
            if choice == '0':
                break
            elif choice == '1':
                await self.enable_exchange()
            elif choice == '2':
                await self.disable_exchange()
            elif choice == '3':
                await self.view_exchange_quotes()
            elif choice == '4':
                await self.view_balances()
            elif choice == '5':
                await self.arbitrage_scanner_menu()
                
            if choice != '0':
                input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.ENDC}")
                
    async def enable_exchange(self):
        """Enable an exchange."""
        exchange = input("Enter exchange name (coinbase/kraken): ").lower()
        
        async with self.session.post(
            f"{API_URL}/api/v1/exchanges/enable/{exchange}",
            headers=self.headers,
            json={"enabled": True}
        ) as resp:
            if resp.status == 200:
                print(f"{Colors.GREEN}✓ {exchange} enabled!{Colors.ENDC}")
            else:
                print(f"{Colors.RED}✗ Failed to enable {exchange}{Colors.ENDC}")
                
    async def disable_exchange(self):
        """Disable an exchange."""
        exchange = input("Enter exchange name (coinbase/kraken): ").lower()
        
        async with self.session.post(
            f"{API_URL}/api/v1/exchanges/enable/{exchange}",
            headers=self.headers,
            json={"enabled": False}
        ) as resp:
            if resp.status == 200:
                print(f"{Colors.GREEN}✓ {exchange} disabled!{Colors.ENDC}")
            else:
                print(f"{Colors.RED}✗ Failed to disable {exchange}{Colors.ENDC}")
                
    async def view_exchange_quotes(self):
        """View quotes across exchanges."""
        symbol = input("Enter symbol (e.g., BTCUSD): ").upper()
        
        async with self.session.get(
            f"{API_URL}/api/v1/exchanges/quotes/{symbol}",
            headers=self.headers
        ) as resp:
            if resp.status == 200:
                result = await resp.json()
                quotes = result.get('quotes', [])
                
                print(f"\n{Colors.BOLD}Quotes for {symbol}:{Colors.ENDC}")
                for quote in quotes:
                    print(f"  {quote['exchange']}: Bid ${quote['bid']:.2f} / Ask ${quote['ask']:.2f} (spread: {quote['spread_pct']:.2%})")
                    
    async def view_balances(self):
        """View balances across exchanges."""
        async with self.session.get(f"{API_URL}/api/v1/exchanges/balances", headers=self.headers) as resp:
            if resp.status == 200:
                result = await resp.json()
                
                print(f"\n{Colors.BOLD}Exchange Balances:{Colors.ENDC}")
                for exchange, balances in result['balances'].items():
                    print(f"\n{exchange}:")
                    for asset, amount in balances.items():
                        if amount > 0:
                            print(f"  {asset}: {amount:.4f}")
                            
                print(f"\nTotal USD Value: ${result['total_usd_value']:.2f}")
                
    async def ml_menu(self):
        """Machine learning menu."""
        while True:
            self.print_header()
            print(f"{Colors.BOLD}Machine Learning{Colors.ENDC}")
            print()
            
            # Get ML status
            async with self.session.get(f"{API_URL}/api/v1/ml/model-status", headers=self.headers) as resp:
                if resp.status == 200:
                    status = await resp.json()
                    print(f"Trained Models: {status['total_models']}")
                    print(f"Symbols: {len(status['trained_symbols'])}")
                    print()
            
            print("1. 🧠 Train ML Models")
            print("2. 🔮 View Predictions")
            print("3. 📊 View ML Signals")
            print("4. 💾 Save Models")
            print("5. 📂 Load Models")
            print("6. 🔄 Start Continuous Training")
            print("0. ⬅️  Back to Main Menu")
            print()
            
            choice = input(f"{Colors.YELLOW}Enter your choice: {Colors.ENDC}")
            
            if choice == '0':
                break
            elif choice == '1':
                await self.train_ml_models()
            elif choice == '2':
                await self.view_ml_predictions()
            elif choice == '3':
                await self.view_ml_signals()
            elif choice == '4':
                await self.save_ml_models()
            elif choice == '5':
                await self.load_ml_models()
            elif choice == '6':
                await self.start_continuous_training()
                
            if choice != '0':
                input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.ENDC}")
                
    async def train_ml_models(self):
        """Train ML models."""
        symbols_input = input("Enter symbols to train (comma-separated, or press Enter for defaults): ")
        
        if symbols_input:
            symbols = [s.strip().upper() for s in symbols_input.split(',')]
        else:
            symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA", "SPY", "BTCUSD", "ETHUSD"]
            
        print(f"\n{Colors.YELLOW}Training ML models for {len(symbols)} symbols...{Colors.ENDC}")
        
        async with self.session.post(
            f"{API_URL}/api/v1/ml/train",
            headers=self.headers,
            json={"symbols": symbols}
        ) as resp:
            if resp.status == 200:
                print(f"{Colors.GREEN}✓ ML training started in background{Colors.ENDC}")
            else:
                print(f"{Colors.RED}✗ Failed to start ML training{Colors.ENDC}")
                
    async def view_ml_predictions(self):
        """View ML predictions."""
        symbol = input("Enter symbol for prediction: ").upper()
        
        async with self.session.get(
            f"{API_URL}/api/v1/ml/predict/{symbol}",
            headers=self.headers,
            params={"time_horizon": 15}
        ) as resp:
            if resp.status == 200:
                pred = await resp.json()
                
                print(f"\n{Colors.BOLD}ML Prediction for {symbol}:{Colors.ENDC}")
                print(f"  Current Price: ${pred['current_price']:.2f}")
                print(f"  Predicted Price: ${pred['predicted_price']:.2f}")
                print(f"  Expected Change: {pred['predicted_change_pct']:.2%}")
                print(f"  Confidence: {pred['confidence']:.1%}")
                print(f"  Time Horizon: {pred['time_horizon_minutes']} minutes")
            else:
                print(f"{Colors.RED}✗ No prediction available for {symbol}{Colors.ENDC}")
                
    async def view_ml_signals(self):
        """View ML trading signals."""
        symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA", "SPY"]
        
        async with self.session.get(
            f"{API_URL}/api/v1/ml/signals",
            headers=self.headers,
            params={"symbols": symbols, "min_confidence": 0.7}
        ) as resp:
            if resp.status == 200:
                result = await resp.json()
                signals = result.get('signals', [])
                
                if signals:
                    print(f"\n{Colors.BOLD}ML Trading Signals:{Colors.ENDC}")
                    for signal in signals[:10]:
                        color = Colors.GREEN if signal['action'] == 'buy' else Colors.RED
                        print(f"  {color}{signal['symbol']}: {signal['action'].upper()} - {signal['predicted_return']:.2%} return (conf: {signal['confidence']:.1%}){Colors.ENDC}")
                else:
                    print(f"{Colors.YELLOW}No ML signals generated{Colors.ENDC}")
                    
    async def save_ml_models(self):
        """Save ML models."""
        async with self.session.post(f"{API_URL}/api/v1/ml/save-models", headers=self.headers) as resp:
            if resp.status == 200:
                print(f"{Colors.GREEN}✓ ML models saved successfully{Colors.ENDC}")
            else:
                print(f"{Colors.RED}✗ Failed to save ML models{Colors.ENDC}")
                
    async def load_ml_models(self):
        """Load ML models."""
        async with self.session.post(f"{API_URL}/api/v1/ml/load-models", headers=self.headers) as resp:
            if resp.status == 200:
                result = await resp.json()
                print(f"{Colors.GREEN}✓ Loaded {result['models_loaded']} ML models{Colors.ENDC}")
            else:
                print(f"{Colors.RED}✗ Failed to load ML models{Colors.ENDC}")
                
    async def start_continuous_training(self):
        """Start continuous ML training."""
        symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA", "SPY"]
        
        async with self.session.post(
            f"{API_URL}/api/v1/ml/start-continuous-training",
            headers=self.headers,
            json={"symbols": symbols}
        ) as resp:
            if resp.status == 200:
                print(f"{Colors.GREEN}✓ Continuous ML training started{Colors.ENDC}")
            else:
                print(f"{Colors.RED}✗ Failed to start continuous training{Colors.ENDC}")
                
    async def run(self):
        """Run the control panel."""
        try:
            while True:
                choice = await self.show_main_menu()
                
                if choice == '0':
                    print(f"\n{Colors.GREEN}Goodbye!{Colors.ENDC}")
                    break
                elif choice == '1':
                    await self.autonomous_trading_menu()
                elif choice == '2':
                    await self.trading_strategies_menu()
                elif choice == '3':
                    await self.exchange_management_menu()
                elif choice == '4':
                    await self.ml_menu()
                elif choice == '5':
                    print(f"{Colors.CYAN}Market analysis coming soon...{Colors.ENDC}")
                    input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.ENDC}")
                elif choice == '6':
                    print(f"{Colors.CYAN}Portfolio management coming soon...{Colors.ENDC}")
                    input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.ENDC}")
                elif choice == '7':
                    print(f"{Colors.CYAN}Advanced features coming soon...{Colors.ENDC}")
                    input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.ENDC}")
                elif choice == '8':
                    print(f"{Colors.CYAN}Opening dashboard at http://localhost:8000/dashboard{Colors.ENDC}")
                    input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.ENDC}")
                elif choice == '9':
                    print(f"{Colors.CYAN}System settings coming soon...{Colors.ENDC}")
                    input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.ENDC}")
                else:
                    print(f"{Colors.RED}Invalid choice!{Colors.ENDC}")
                    await asyncio.sleep(1)
                    
        except KeyboardInterrupt:
            print(f"\n{Colors.YELLOW}Interrupted by user{Colors.ENDC}")
        except Exception as e:
            print(f"\n{Colors.RED}Error: {e}{Colors.ENDC}")


async def main():
    """Main entry point."""
    async with TradingBotControlPanel() as panel:
        await panel.run()


if __name__ == "__main__":
    asyncio.run(main())