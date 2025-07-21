#!/usr/bin/env python3
"""Start remote control bots for Discord and Telegram."""
import asyncio
import os
import sys
from multiprocessing import Process

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.remote_control.discord_bot import run_discord_bot
from app.services.remote_control.telegram_bot import run_telegram_bot
from app.monitoring.logger import get_logger

logger = get_logger(__name__)

# ANSI color codes
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
BLUE = '\033[94m'
ENDC = '\033[0m'
BOLD = '\033[1m'


def check_config():
    """Check if bot tokens are configured."""
    discord_token = os.getenv("DISCORD_BOT_TOKEN")
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    
    if not discord_token and not telegram_token:
        print(f"{RED}❌ No bot tokens configured!{ENDC}")
        print(f"\nPlease add to your .env file:")
        print(f"{YELLOW}DISCORD_BOT_TOKEN=your_discord_bot_token")
        print(f"DISCORD_CONTROL_CHANNEL_ID=your_channel_id")
        print(f"TELEGRAM_BOT_TOKEN=your_telegram_bot_token")
        print(f"TELEGRAM_CHAT_ID=your_chat_id{ENDC}")
        print(f"\n{BLUE}How to get tokens:{ENDC}")
        print(f"Discord: https://discord.com/developers/applications")
        print(f"Telegram: Talk to @BotFather on Telegram")
        return False
        
    return True


def run_discord_process():
    """Run Discord bot in a separate process."""
    try:
        print(f"{GREEN}🎮 Starting Discord bot...{ENDC}")
        run_discord_bot()
    except Exception as e:
        print(f"{RED}Discord bot error: {e}{ENDC}")


def run_telegram_process():
    """Run Telegram bot in a separate process."""
    try:
        print(f"{GREEN}💬 Starting Telegram bot...{ENDC}")
        run_telegram_bot()
    except Exception as e:
        print(f"{RED}Telegram bot error: {e}{ENDC}")


def main():
    """Main function."""
    print(f"\n{BOLD}🤖 TRADING BOT REMOTE CONTROL{ENDC}")
    print("=" * 50)
    
    if not check_config():
        return
        
    discord_token = os.getenv("DISCORD_BOT_TOKEN")
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    
    processes = []
    
    print(f"\n{YELLOW}Starting remote control bots...{ENDC}\n")
    
    # Start Discord bot if configured
    if discord_token:
        discord_process = Process(target=run_discord_process)
        discord_process.start()
        processes.append(discord_process)
        print(f"{GREEN}✓ Discord bot process started{ENDC}")
    else:
        print(f"{YELLOW}⚠ Discord bot not configured{ENDC}")
        
    # Start Telegram bot if configured
    if telegram_token:
        telegram_process = Process(target=run_telegram_process)
        telegram_process.start()
        processes.append(telegram_process)
        print(f"{GREEN}✓ Telegram bot process started{ENDC}")
    else:
        print(f"{YELLOW}⚠ Telegram bot not configured{ENDC}")
        
    if not processes:
        print(f"\n{RED}No bots to run!{ENDC}")
        return
        
    print(f"\n{GREEN}{BOLD}✅ REMOTE CONTROL ACTIVE!{ENDC}")
    print(f"\n{BLUE}Bot Controls:{ENDC}")
    
    if discord_token:
        print(f"• Discord: Check your configured channel")
        
    if telegram_token:
        print(f"• Telegram: Send /start to your bot")
        
    print(f"\n{YELLOW}Press Ctrl+C to stop all bots{ENDC}")
    
    try:
        # Wait for all processes
        for p in processes:
            p.join()
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Stopping bots...{ENDC}")
        for p in processes:
            p.terminate()
            p.join()
        print(f"{GREEN}✓ All bots stopped{ENDC}")


if __name__ == "__main__":
    main()