#!/bin/bash

# 🚀 Trademk1 Trading Bot Startup Script

echo "🚀 Starting Trademk1 Trading Bot..."
echo "=================================="

# Check if .env file exists
if [ ! -f .env ]; then
    echo "❌ .env file not found!"
    echo "📝 Copying .env.example to .env..."
    cp .env.example .env
    echo ""
    echo "⚠️  IMPORTANT: Please edit .env file with your Alpaca API keys:"
    echo "   - ALPACA_API_KEY=your_api_key"
    echo "   - ALPACA_API_SECRET=your_secret"
    echo ""
    echo "💡 Get free Alpaca paper trading keys at: https://alpaca.markets/"
    echo ""
    read -p "Press Enter after updating .env file..."
fi

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

echo "🐳 Starting Docker services..."
docker compose up --build -d

echo "⏳ Waiting for services to start (30 seconds)..."
sleep 30

echo "🔍 Checking service health..."

# Check if app is responding
if curl -s http://localhost:8000/api/health > /dev/null; then
    echo "✅ API is running at http://localhost:8000"
else
    echo "❌ API is not responding. Check logs with: docker compose logs app"
    exit 1
fi

# Check database
if curl -s http://localhost:8000/api/health/detailed | grep -q "healthy"; then
    echo "✅ Database is connected"
else
    echo "⚠️  Database might have issues. Check logs with: docker compose logs db"
fi

echo ""
echo "🎉 Trademk1 Trading Bot is running!"
echo "=================================="
echo ""
echo "📚 Quick Start:"
echo "   1. API Documentation: http://localhost:8000/api/docs/"
echo "   2. Health Check: http://localhost:8000/api/health/detailed"
echo "   3. QuestDB Console: http://localhost:9000"
echo ""
echo "🔧 Next Steps:"
echo "   1. Register a user account (see STARTUP_GUIDE.md)"
echo "   2. Get JWT token for authentication"
echo "   3. Submit trading signals or create strategies"
echo ""
echo "📖 Full guide: cat STARTUP_GUIDE.md"
echo ""
echo "🛑 To stop: docker compose down"
echo "📋 View logs: docker compose logs -f app"
echo ""
echo "Happy trading! 📈"