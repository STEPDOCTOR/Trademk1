"""Discord bot for remote control of the trading system."""
import discord
from discord.ext import commands
import asyncio
import aiohttp
import json
import os
from datetime import datetime
from typing import Dict, Any, Optional

from app.monitoring.logger import get_logger
from app.config.settings import get_settings

logger = get_logger(__name__)
settings = get_settings()

# Discord bot token from environment
DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CONTROL_CHANNEL_ID", "0"))
API_URL = "http://localhost:8000"


class TradingControlView(discord.ui.View):
    """Discord UI View with buttons for trading control."""
    
    def __init__(self, bot_instance):
        super().__init__(timeout=None)  # Persistent view
        self.bot = bot_instance
        
    @discord.ui.button(label="🟢 Start Bot", style=discord.ButtonStyle.success, custom_id="start_bot")
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        result = await self.bot.start_autonomous_trading()
        
        embed = discord.Embed(
            title="✅ Bot Started",
            description=result.get("message", "Autonomous trading started"),
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        await interaction.followup.send(embed=embed)
        
    @discord.ui.button(label="🔴 Stop Bot", style=discord.ButtonStyle.danger, custom_id="stop_bot")
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        result = await self.bot.stop_autonomous_trading()
        
        embed = discord.Embed(
            title="🛑 Bot Stopped",
            description=result.get("message", "Autonomous trading stopped"),
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )
        await interaction.followup.send(embed=embed)
        
    @discord.ui.button(label="📊 Status", style=discord.ButtonStyle.primary, custom_id="bot_status")
    async def status_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        status = await self.bot.get_full_status()
        
        embed = discord.Embed(
            title="🤖 Trading Bot Status",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        # Autonomous status
        auto_status = status.get("autonomous", {})
        embed.add_field(
            name="🔄 Autonomous Trading",
            value="🟢 Running" if auto_status.get("running") else "🔴 Stopped",
            inline=True
        )
        
        # Positions
        positions = status.get("positions", {})
        embed.add_field(
            name="💼 Positions",
            value=f"{positions.get('count', 0)} active",
            inline=True
        )
        
        # P&L
        performance = status.get("performance", {})
        pnl = performance.get("daily_pnl", 0)
        embed.add_field(
            name="💰 Daily P&L",
            value=f"${pnl:+,.2f}",
            inline=True
        )
        
        # Enabled strategies
        strategies = auto_status.get("strategies", {})
        enabled = [s for s, config in strategies.items() if config.get("enabled")]
        if enabled:
            embed.add_field(
                name="🎯 Active Strategies",
                value=", ".join(enabled),
                inline=False
            )
        
        await interaction.followup.send(embed=embed)
        
    @discord.ui.button(label="⚡ Force Trade", style=discord.ButtonStyle.secondary, custom_id="force_trade")
    async def force_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        result = await self.bot.force_trading_cycle()
        
        embed = discord.Embed(
            title="⚡ Trading Cycle Executed",
            description=f"Generated {result.get('signals_count', 0)} signals",
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )
        await interaction.followup.send(embed=embed)
        
    @discord.ui.button(label="📈 Performance", style=discord.ButtonStyle.secondary, custom_id="performance")
    async def performance_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        perf = await self.bot.get_performance()
        
        embed = discord.Embed(
            title="📈 Performance Summary",
            color=discord.Color.green() if perf.get("total_pnl", 0) >= 0 else discord.Color.red(),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(name="💵 Total P&L", value=f"${perf.get('total_pnl', 0):+,.2f}", inline=True)
        embed.add_field(name="📊 Win Rate", value=f"{perf.get('win_rate', 0):.1%}", inline=True)
        embed.add_field(name="🔢 Total Trades", value=str(perf.get('total_trades', 0)), inline=True)
        embed.add_field(name="📈 Best Trade", value=f"${perf.get('best_trade', 0):+,.2f}", inline=True)
        embed.add_field(name="📉 Worst Trade", value=f"${perf.get('worst_trade', 0):+,.2f}", inline=True)
        embed.add_field(name="💎 Sharpe Ratio", value=f"{perf.get('sharpe_ratio', 0):.2f}", inline=True)
        
        await interaction.followup.send(embed=embed)


class StrategyControlView(discord.ui.View):
    """View for strategy control."""
    
    def __init__(self, bot_instance):
        super().__init__(timeout=None)
        self.bot = bot_instance
        
    @discord.ui.button(label="🚀 Aggressive Mode", style=discord.ButtonStyle.danger, custom_id="aggressive")
    async def aggressive_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.bot.set_aggressive_mode()
        
        embed = discord.Embed(
            title="🚀 Aggressive Mode Activated",
            description="Trading with aggressive settings:\n• 0.1% momentum threshold\n• 2% stop loss\n• 5% take profit\n• ML enabled\n• Up to 30 positions",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )
        await interaction.followup.send(embed=embed)
        
    @discord.ui.button(label="🛡️ Conservative Mode", style=discord.ButtonStyle.success, custom_id="conservative")
    async def conservative_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.bot.set_conservative_mode()
        
        embed = discord.Embed(
            title="🛡️ Conservative Mode Activated",
            description="Trading with conservative settings:\n• 3% momentum threshold\n• 5% stop loss\n• 15% take profit\n• Technical analysis only\n• Max 10 positions",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        await interaction.followup.send(embed=embed)
        
    @discord.ui.button(label="🧠 Enable ML", style=discord.ButtonStyle.primary, custom_id="enable_ml")
    async def ml_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.bot.enable_ml_trading()
        
        embed = discord.Embed(
            title="🧠 Machine Learning Enabled",
            description="ML predictions activated with:\n• 70% confidence threshold\n• 0.3% minimum return\n• Continuous training",
            color=discord.Color.purple(),
            timestamp=datetime.utcnow()
        )
        await interaction.followup.send(embed=embed)
        
    @discord.ui.button(label="📰 Enable News Trading", style=discord.ButtonStyle.primary, custom_id="news_trading")
    async def news_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.bot.enable_news_trading()
        
        embed = discord.Embed(
            title="📰 News Trading Enabled",
            description="Trading based on news sentiment analysis",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        await interaction.followup.send(embed=embed)


class TradingBot(commands.Bot):
    """Discord bot for trading control."""
    
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)
        self.token = None
        self.api_headers = None
        
    async def setup_hook(self):
        """Setup persistent views."""
        self.add_view(TradingControlView(self))
        self.add_view(StrategyControlView(self))
        
    async def on_ready(self):
        """Bot is ready."""
        logger.info(f'Discord bot logged in as {self.user}')
        
        # Login to trading API
        await self.login_to_api()
        
        # Send control panel to designated channel
        if DISCORD_CHANNEL_ID:
            channel = self.get_channel(DISCORD_CHANNEL_ID)
            if channel:
                await self.send_control_panel(channel)
                
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
                    self.token = result["access_token"]
                    self.api_headers = {"Authorization": f"Bearer {self.token}"}
                    logger.info("Successfully logged in to trading API")
                else:
                    logger.error("Failed to login to trading API")
                    
    async def send_control_panel(self, channel):
        """Send the main control panel."""
        embed = discord.Embed(
            title="🤖 Trademk1 Trading Bot Control Panel",
            description="Control your trading bot with the buttons below",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="📌 Main Controls",
            value="Start/stop the bot and check status",
            inline=False
        )
        
        embed.add_field(
            name="⚙️ Strategy Controls",
            value="Switch between trading modes",
            inline=False
        )
        
        # Clear channel and send new panels
        await channel.purge(limit=10)
        
        await channel.send(embed=embed, view=TradingControlView(self))
        
        # Strategy control panel
        strategy_embed = discord.Embed(
            title="🎯 Strategy Control Panel",
            description="Configure trading strategies",
            color=discord.Color.purple()
        )
        await channel.send(embed=strategy_embed, view=StrategyControlView(self))
        
    # API Methods
    
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


# Commands for additional control
@commands.command()
async def positions(ctx):
    """Show current positions."""
    bot = ctx.bot
    status = await bot.get_full_status()
    positions = status.get("positions", {}).get("data", [])
    
    if not positions:
        await ctx.send("No active positions")
        return
        
    embed = discord.Embed(title="📊 Current Positions", color=discord.Color.blue())
    
    for pos in positions[:10]:  # Limit to 10
        value = f"Qty: {pos['qty']} | P&L: ${pos.get('unrealized_pnl', 0):+,.2f}"
        embed.add_field(name=pos['symbol'], value=value, inline=True)
        
    await ctx.send(embed=embed)


def run_discord_bot():
    """Run the Discord bot."""
    bot = TradingBot()
    bot.add_command(positions)
    
    if DISCORD_TOKEN:
        bot.run(DISCORD_TOKEN)
    else:
        logger.error("DISCORD_BOT_TOKEN not set in environment")