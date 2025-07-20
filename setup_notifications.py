#!/usr/bin/env python3
"""Setup script for configuring Telegram and Discord notifications."""
import os
import sys

print("🔔 Notification Setup for Trading Bot")
print("="*50)
print()
print("This script will help you set up real-time notifications")
print("for your trading bot via Telegram and/or Discord.")
print()

# Check if .env exists
env_file = ".env"
if not os.path.exists(env_file):
    print("⚠️  Warning: .env file not found. Creating one...")
    with open(env_file, 'w') as f:
        f.write("# Notification settings will be added below\n")

# Read existing .env
with open(env_file, 'r') as f:
    env_content = f.read()

updates = []

# Telegram Setup
print("1️⃣  TELEGRAM SETUP")
print("-"*30)
print("To get notifications on Telegram:")
print("1. Open Telegram and search for @BotFather")
print("2. Send /newbot and follow instructions")
print("3. Copy the bot token you receive")
print("4. Start a chat with your bot")
print("5. Send any message to the bot")
print("6. Visit: https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates")
print("7. Find your chat ID in the response")
print()

setup_telegram = input("Do you want to set up Telegram notifications? (y/n): ").lower() == 'y'

if setup_telegram:
    telegram_token = input("Enter your Telegram bot token: ").strip()
    telegram_chat_id = input("Enter your Telegram chat ID: ").strip()
    
    if telegram_token and telegram_chat_id:
        updates.append(f"TELEGRAM_BOT_TOKEN={telegram_token}")
        updates.append(f"TELEGRAM_CHAT_ID={telegram_chat_id}")
        print("✅ Telegram configuration saved")
    else:
        print("❌ Skipping Telegram setup (missing information)")
else:
    print("⏭️  Skipping Telegram setup")

print()

# Discord Setup
print("2️⃣  DISCORD SETUP")
print("-"*30)
print("To get notifications on Discord:")
print("1. Open Discord and go to your server")
print("2. Right-click on a channel → Edit Channel")
print("3. Go to 'Integrations' → 'Webhooks'")
print("4. Click 'New Webhook'")
print("5. Name it 'Trading Bot' and copy the webhook URL")
print()

setup_discord = input("Do you want to set up Discord notifications? (y/n): ").lower() == 'y'

if setup_discord:
    discord_webhook = input("Enter your Discord webhook URL: ").strip()
    
    if discord_webhook:
        updates.append(f"DISCORD_WEBHOOK_URL={discord_webhook}")
        print("✅ Discord configuration saved")
    else:
        print("❌ Skipping Discord setup (missing webhook URL)")
else:
    print("⏭️  Skipping Discord setup")

# Write updates to .env
if updates:
    print()
    print("📝 Updating .env file...")
    
    # Remove existing notification settings
    lines = env_content.split('\n')
    filtered_lines = [line for line in lines if not any(
        line.startswith(prefix) for prefix in [
            'TELEGRAM_BOT_TOKEN=',
            'TELEGRAM_CHAT_ID=',
            'DISCORD_WEBHOOK_URL='
        ]
    )]
    
    # Add new settings
    with open(env_file, 'w') as f:
        f.write('\n'.join(filtered_lines))
        if not env_content.endswith('\n'):
            f.write('\n')
        f.write('\n# Notification Settings\n')
        for update in updates:
            f.write(f"{update}\n")
    
    print("✅ Configuration saved to .env file")
    print()
    print("🎉 Notification setup complete!")
    print()
    print("You will receive notifications for:")
    print("  • Trade executions (buy/sell)")
    print("  • Stop loss and take profit hits")
    print("  • Trailing stop adjustments")
    print("  • Daily limit warnings and hits")
    print("  • Bot start/stop events")
    print()
    print("To test notifications, restart the bot:")
    print("  docker compose restart app")
    print()
else:
    print()
    print("❌ No notifications configured")
    print("Run this script again when you're ready to set up notifications")

# Test notifications
if updates and (setup_telegram or setup_discord):
    test = input("Would you like to send a test notification? (y/n): ").lower() == 'y'
    
    if test:
        print()
        print("To send a test notification, the bot must be running.")
        print("After restarting the bot, you can test with:")
        print()
        print("curl -X POST http://localhost:8000/api/v1/notifications/test \\")
        print("  -H 'Content-Type: application/json' \\")
        print("  -d '{\"message\": \"Test notification from Trading Bot\"}'")
        print()