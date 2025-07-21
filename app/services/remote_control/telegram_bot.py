"""Telegram bot for remote control of the trading system."""
import asyncio
import aiohttp
import json
import os
from datetime import datetime
from typing import Dict, Any, Optional, List
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode

from app.monitoring.logger import get_logger
from app.config.settings import get_settings

logger = get_logger(__name__)
settings = get_settings()

# Telegram bot configuration
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
API_URL = "http://localhost:8000"


class TradingBotTelegram:
    """Telegram bot for trading control."""
    
    def __init__(self):
        self.token = TELEGRAM_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.api_token = None
        self.api_headers = None
        self.app = None
        
    async def setup(self):
        """Setup the bot."""
        if not self.token:
            logger.error("TELEGRAM_BOT_TOKEN not set in environment")
            return False
            
        # Create bot application
        self.app = Application.builder().token(self.token).build()
        
        # Add handlers
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("help", self.cmd_help))
        self.app.add_handler(CommandHandler("status", self.cmd_status))
        self.app.add_handler(CommandHandler("positions", self.cmd_positions))
        self.app.add_handler(CommandHandler("performance", self.cmd_performance))
        self.app.add_handler(CommandHandler("control", self.cmd_control_panel))
        
        # Callback handlers for buttons
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))
        
        # Login to API
        await self.login_to_api()
        
        return True
        
    async def login_to_api(self):
        """Login to trading API."""
        async with aiohttp.ClientSession() as session:
            login_data = {
                "username": os.getenv("TRADING_API_USER", "testuser@example.com"),
                "password": os.getenv("TRADING_API_PASS", "Test123!@#")
            }
            
            async with session.post(f"{API_URL}/api/v1/auth/login", data=login_data) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    self.api_token = result["access_token"]
                    self.api_headers = {"Authorization": f"Bearer {self.api_token}"}
                    logger.info("Successfully logged in to trading API")
                else:
                    logger.error("Failed to login to trading API")
                    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        welcome_msg = (
            "🤖 *Welcome to Trademk1 Trading Bot!*\n\n"
            "I can help you control your trading bot remotely.\n\n"
            "Available commands:\n"
            "/control - 🎮 Show control panel\n"
            "/status - 📊 Check bot status\n"
            "/positions - 💼 View positions\n"
            "/performance - 📈 View performance\n"
            "/help - ❓ Show this help message"
        )
        
        await update.message.reply_text(
            welcome_msg,
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Show control panel
        await self.cmd_control_panel(update, context)
        
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        help_text = (
            "📚 *Trading Bot Commands*\n\n"
            "🎮 *Control*\n"
            "/control - Main control panel\n\n"
            "📊 *Monitoring*\n"
            "/status - Bot status\n"
            "/positions - Current positions\n"
            "/performance - Performance metrics\n\n"
            "💡 *Tips*\n"
            "• Use the control panel buttons for easy access\n"
            "• The bot runs 24/7 automatically\n"
            "• Check performance daily\n"
            "• Adjust strategies as needed"
        )
        
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
        
    async def cmd_control_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show main control panel."""
        # Main control buttons
        keyboard = [
            [
                InlineKeyboardButton("🟢 Start Bot", callback_data="start_bot"),
                InlineKeyboardButton("🔴 Stop Bot", callback_data="stop_bot")
            ],
            [
                InlineKeyboardButton("📊 Status", callback_data="status"),
                InlineKeyboardButton("⚡ Force Trade", callback_data="force_trade")
            ],
            [
                InlineKeyboardButton("🚀 Aggressive Mode", callback_data="aggressive_mode"),
                InlineKeyboardButton("🛡️ Conservative Mode", callback_data="conservative_mode")
            ],
            [
                InlineKeyboardButton("🧠 Enable ML", callback_data="enable_ml"),
                InlineKeyboardButton("📰 News Trading", callback_data="news_trading")
            ],
            [
                InlineKeyboardButton("💼 Positions", callback_data="positions"),
                InlineKeyboardButton("📈 Performance", callback_data="performance")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        msg = (
            "🎮 *Trading Bot Control Panel*\n\n"
            "Choose an action below:"
        )
        
        await update.message.reply_text(
            msg,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
        
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command."""
        status = await self.get_full_status()
        
        # Format status message
        auto_status = status.get("autonomous", {})
        positions = status.get("positions", {})
        performance = status.get("performance", {})
        
        running = "🟢 Running" if auto_status.get("running") else "🔴 Stopped"
        
        enabled_strategies = [s for s, c in auto_status.get("strategies", {}).items() if c.get("enabled")]
        strategies_text = ", ".join(enabled_strategies) if enabled_strategies else "None"
        
        msg = (
            f"📊 *Trading Bot Status*\n\n"
            f"*Autonomous Trading:* {running}\n"
            f"*Active Strategies:* {strategies_text}\n"
            f"*Positions:* {positions.get('count', 0)}\n"
            f"*Daily P&L:* ${performance.get('daily_pnl', 0):+,.2f}\n"
            f"\n_Last updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC_"
        )
        
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        
    async def cmd_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /positions command."""
        status = await self.get_full_status()
        positions = status.get("positions", {}).get("data", [])
        
        if not positions:
            await update.message.reply_text("📊 No active positions")
            return
            
        msg = "💼 *Current Positions*\n\n"
        
        for pos in positions[:10]:  # Limit to 10
            pnl = pos.get('unrealized_pnl', 0)
            pnl_emoji = "🟢" if pnl >= 0 else "🔴"
            
            msg += (
                f"{pnl_emoji} *{pos['symbol']}*\n"
                f"  Qty: {pos['qty']} | P&L: ${pnl:+,.2f}\n\n"
            )
            
        if len(positions) > 10:
            msg += f"_... and {len(positions) - 10} more positions_"
            
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        
    async def cmd_performance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /performance command."""
        perf = await self.get_performance()
        
        total_pnl = perf.get('total_pnl', 0)
        pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"
        
        msg = (
            f"📈 *Performance Summary*\n\n"
            f"{pnl_emoji} *Total P&L:* ${total_pnl:+,.2f}\n"
            f"📊 *Win Rate:* {perf.get('win_rate', 0):.1%}\n"
            f"🔢 *Total Trades:* {perf.get('total_trades', 0)}\n"
            f"📈 *Best Trade:* ${perf.get('best_trade', 0):+,.2f}\n"
            f"📉 *Worst Trade:* ${perf.get('worst_trade', 0):+,.2f}\n"
            f"💎 *Sharpe Ratio:* {perf.get('sharpe_ratio', 0):.2f}\n"
            f"\n_Performance as of {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC_"
        )
        
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks."""
        query = update.callback_query
        await query.answer()
        
        action = query.data
        
        if action == "start_bot":
            result = await self.start_autonomous_trading()
            msg = "✅ *Bot Started!*\n\nAutonomous trading is now active."
            
        elif action == "stop_bot":
            result = await self.stop_autonomous_trading()
            msg = "🛑 *Bot Stopped!*\n\nAutonomous trading has been stopped."
            
        elif action == "status":
            await self.cmd_status(query, context)
            return
            
        elif action == "force_trade":
            result = await self.force_trading_cycle()
            signals = result.get('signals_count', 0)
            msg = f"⚡ *Trading Cycle Executed!*\n\nGenerated {signals} trading signals."
            
        elif action == "aggressive_mode":
            await self.set_aggressive_mode()
            msg = (
                "🚀 *Aggressive Mode Activated!*\n\n"
                "Trading with:\n"
                "• 0.1% momentum threshold\n"
                "• 2% stop loss / 5% take profit\n"
                "• ML predictions enabled\n"
                "• Up to 30 positions"
            )
            
        elif action == "conservative_mode":
            await self.set_conservative_mode()
            msg = (
                "🛡️ *Conservative Mode Activated!*\n\n"
                "Trading with:\n"
                "• 3% momentum threshold\n"
                "• 5% stop loss / 15% take profit\n"
                "• Technical analysis only\n"
                "• Max 10 positions"
            )
            
        elif action == "enable_ml":
            await self.enable_ml_trading()
            msg = (
                "🧠 *Machine Learning Enabled!*\n\n"
                "ML predictions activated with:\n"
                "• 70% confidence threshold\n"
                "• 0.3% minimum return\n"
                "• Continuous training"
            )
            
        elif action == "news_trading":
            await self.enable_news_trading()
            msg = "📰 *News Trading Enabled!*\n\nTrading based on news sentiment analysis."
            
        elif action == "positions":
            await self.cmd_positions(query, context)
            return
            
        elif action == "performance":
            await self.cmd_performance(query, context)
            return
            
        else:
            msg = "❓ Unknown action"
            
        await query.edit_message_text(
            text=msg,
            parse_mode=ParseMode.MARKDOWN
        )
        
    # API Methods (same as Discord bot)
    
    async def start_autonomous_trading(self) -> Dict[str, Any]:
        """Start autonomous trading."""
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{API_URL}/api/v1/autonomous/start", headers=self.api_headers) as resp:
                if resp.status == 200:
                    return await resp.json()
                return {"message": "Failed to start trading"}
                
    async def stop_autonomous_trading(self) -> Dict[str, Any]:
        """Stop autonomous trading."""
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{API_URL}/api/v1/autonomous/stop", headers=self.api_headers) as resp:
                if resp.status == 200:
                    return await resp.json()
                return {"message": "Failed to stop trading"}
                
    async def get_full_status(self) -> Dict[str, Any]:
        """Get comprehensive status."""
        status = {}
        
        async with aiohttp.ClientSession() as session:
            # Autonomous status
            async with session.get(f"{API_URL}/api/v1/autonomous/status", headers=self.api_headers) as resp:
                if resp.status == 200:
                    status["autonomous"] = await resp.json()
                    
            # Positions
            async with session.get(f"{API_URL}/api/v1/trading/positions", headers=self.api_headers) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    status["positions"] = {
                        "count": len(result.get("positions", [])),
                        "data": result.get("positions", [])
                    }
                    
            # Performance
            async with session.get(f"{API_URL}/api/v1/performance/daily", headers=self.api_headers) as resp:
                if resp.status == 200:
                    status["performance"] = await resp.json()
                    
        return status
        
    async def force_trading_cycle(self) -> Dict[str, Any]:
        """Force a trading cycle."""
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{API_URL}/api/v1/autonomous/force-cycle", headers=self.api_headers) as resp:
                if resp.status == 200:
                    return await resp.json()
                return {"signals_count": 0}
                
    async def get_performance(self) -> Dict[str, Any]:
        """Get performance metrics."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_URL}/api/v1/performance/summary", headers=self.api_headers) as resp:
                if resp.status == 200:
                    return await resp.json()
                return {}
                
    async def set_aggressive_mode(self):
        """Set aggressive trading mode."""
        strategies = {
            "momentum": {"enabled": True, "momentum_threshold": 0.001, "max_positions": 30},
            "stop_loss": {"enabled": True, "stop_loss_pct": 0.02},
            "take_profit": {"enabled": True, "take_profit_pct": 0.05},
            "technical_analysis": {"enabled": True, "min_confidence": 0.5},
            "ml_prediction": {"enabled": True, "min_confidence": 0.65, "min_return": 0.002}
        }
        
        async with aiohttp.ClientSession() as session:
            for strategy, config in strategies.items():
                await session.patch(
                    f"{API_URL}/api/v1/autonomous/strategy/{strategy}",
                    headers=self.api_headers,
                    json=config
                )
                
    async def set_conservative_mode(self):
        """Set conservative trading mode."""
        strategies = {
            "momentum": {"enabled": True, "momentum_threshold": 0.03, "max_positions": 10},
            "stop_loss": {"enabled": True, "stop_loss_pct": 0.05},
            "take_profit": {"enabled": True, "take_profit_pct": 0.15},
            "technical_analysis": {"enabled": True, "min_confidence": 0.7},
            "ml_prediction": {"enabled": False}
        }
        
        async with aiohttp.ClientSession() as session:
            for strategy, config in strategies.items():
                await session.patch(
                    f"{API_URL}/api/v1/autonomous/strategy/{strategy}",
                    headers=self.api_headers,
                    json=config
                )
                
    async def enable_ml_trading(self):
        """Enable ML trading."""
        async with aiohttp.ClientSession() as session:
            # Train models
            symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA", "SPY"]
            await session.post(
                f"{API_URL}/api/v1/ml/train",
                headers=self.api_headers,
                json={"symbols": symbols}
            )
            
            # Enable ML strategy
            await session.patch(
                f"{API_URL}/api/v1/autonomous/strategy/ml_prediction",
                headers=self.api_headers,
                json={"enabled": True, "min_confidence": 0.7, "min_return": 0.003}
            )
            
    async def enable_news_trading(self):
        """Enable news-based trading."""
        async with aiohttp.ClientSession() as session:
            await session.patch(
                f"{API_URL}/api/v1/autonomous/strategy/news_sentiment",
                headers=self.api_headers,
                json={"enabled": True}
            )
            
    async def send_notification(self, message: str, parse_mode: str = ParseMode.MARKDOWN):
        """Send notification to configured chat."""
        if not self.chat_id:
            return
            
        try:
            bot = Bot(token=self.token)
            await bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode=parse_mode
            )
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
            
    async def run(self):
        """Run the bot."""
        if not await self.setup():
            return
            
        # Send startup notification
        await self.send_notification(
            "🚀 *Trading Bot Started!*\n\n"
            "Telegram control interface is now active.\n"
            "Type /control to see the control panel."
        )
        
        # Start polling
        await self.app.run_polling()


def run_telegram_bot():
    """Run the Telegram bot."""
    bot = TradingBotTelegram()
    asyncio.run(bot.run())


if __name__ == "__main__":
    run_telegram_bot()