# Remote Control Setup Guide

Control your Trademk1 trading bot from Discord or Telegram with push-button controls!

## 🎮 Discord Bot Setup

### 1. Create Discord Application
1. Go to https://discord.com/developers/applications
2. Click "New Application" and give it a name (e.g., "Trademk1 Bot")
3. Go to the "Bot" section
4. Click "Add Bot"
5. Copy the bot token

### 2. Add Bot to Your Server
1. In the Discord Developer Portal, go to OAuth2 > URL Generator
2. Select scopes: `bot`
3. Select permissions: `Send Messages`, `Read Message History`, `Use Slash Commands`
4. Copy the generated URL and open it in your browser
5. Select your server and authorize the bot

### 3. Configure Environment
Add to your `.env` file:
```bash
DISCORD_BOT_TOKEN=your_bot_token_here
DISCORD_CONTROL_CHANNEL_ID=your_channel_id_here
```

To get the channel ID:
1. Enable Developer Mode in Discord (Settings > Advanced > Developer Mode)
2. Right-click on the channel where you want the bot
3. Click "Copy Channel ID"

## 💬 Telegram Bot Setup

### 1. Create Telegram Bot
1. Open Telegram and search for @BotFather
2. Send `/newbot` to BotFather
3. Choose a name for your bot (e.g., "Trademk1 Trading Bot")
4. Choose a username (must end in "bot", e.g., "trademk1_bot")
5. Copy the bot token BotFather gives you

### 2. Get Your Chat ID
1. Send a message to your new bot
2. Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
3. Find your chat ID in the response

### 3. Configure Environment
Add to your `.env` file:
```bash
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

## 🚀 Starting Remote Control

### Option 1: Start Both Bots
```bash
# Make executable
chmod +x start_remote_control.py

# Start both Discord and Telegram bots
./start_remote_control.py
```

### Option 2: Start Individual Bots
```bash
# Discord only
python -m app.services.remote_control.discord_bot

# Telegram only
python -m app.services.remote_control.telegram_bot
```

### Option 3: Run as Background Service
```bash
# Using nohup
nohup ./start_remote_control.py > remote_control.log 2>&1 &

# Or using screen
screen -S trading-remote
./start_remote_control.py
# Press Ctrl+A, D to detach
```

## 📱 Using the Bots

### Discord Commands
Once the bot is in your channel, it will post a control panel with buttons:
- 🟢 **Start Bot** - Start autonomous trading
- 🔴 **Stop Bot** - Stop autonomous trading
- 📊 **Status** - Check current status
- ⚡ **Force Trade** - Execute immediate trading cycle
- 🚀 **Aggressive Mode** - High-frequency trading
- 🛡️ **Conservative Mode** - Safe trading settings
- 🧠 **Enable ML** - Activate machine learning
- 📰 **Enable News Trading** - Trade on news sentiment

Additional commands:
- `!positions` - View current positions

### Telegram Commands
Start a chat with your bot and use:
- `/start` - Show welcome message and control panel
- `/control` - Show main control panel
- `/status` - Check bot status
- `/positions` - View current positions
- `/performance` - View performance metrics
- `/help` - Show help message

All controls are also available as inline buttons!

## 🔧 Advanced Configuration

### Auto-Start on Boot
Add to your system startup:
```bash
# Add to crontab
crontab -e

# Add this line
@reboot /home/aeden/Trademk1/start_remote_control.py
```

### Systemd Service
Create `/etc/systemd/system/trading-remote.service`:
```ini
[Unit]
Description=Trademk1 Remote Control Bots
After=network.target

[Service]
Type=simple
User=aeden
WorkingDirectory=/home/aeden/Trademk1
ExecStart=/home/aeden/Trademk1/start_remote_control.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable trading-remote
sudo systemctl start trading-remote
```

## 🛡️ Security Best Practices

1. **Keep Tokens Secret**
   - Never commit tokens to git
   - Use environment variables only
   - Rotate tokens regularly

2. **Limit Access**
   - Discord: Use private channels
   - Telegram: Only respond to your chat ID

3. **Monitor Activity**
   - Check logs regularly
   - Set up alerts for unusual activity

## 🆘 Troubleshooting

### Bot Not Responding?
1. Check if the main trading app is running:
   ```bash
   docker compose ps
   ```

2. Check bot logs:
   ```bash
   # If using start_remote_control.py
   tail -f remote_control.log
   
   # Docker logs
   docker compose logs app
   ```

3. Verify tokens are correct in `.env`

4. Ensure network connectivity

### Permission Errors?
- Discord: Re-invite bot with correct permissions
- Telegram: Make sure you're using the correct chat ID

### Commands Not Working?
1. Restart the bots
2. Check API authentication
3. Verify the trading app is accessible at http://localhost:8000

## 📊 Monitoring

The bots will send notifications for:
- Startup/shutdown events
- Critical errors
- Large profit/loss events (configurable)
- Position limit warnings

## 🎯 Quick Start Example

1. Add to `.env`:
```bash
DISCORD_BOT_TOKEN=YOUR_DISCORD_TOKEN
TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_TOKEN
TELEGRAM_CHAT_ID=YOUR_CHAT_ID
```

2. Start the bots:
```bash
./start_remote_control.py
```

3. In Discord/Telegram, click "🟢 Start Bot" button

That's it! Your bot is now trading autonomously and can be controlled remotely! 🚀