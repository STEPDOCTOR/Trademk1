#!/bin/bash

# 🚀 Trademk1 One-Click Startup Script
# This script automates the entire startup process

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
DEFAULT_EMAIL="trader@example.com"
DEFAULT_PASSWORD="TradingBot123!"
DEFAULT_NAME="Trading Bot User"

echo -e "${BLUE}🚀 Trademk1 Automated Startup${NC}"
echo "=================================="

# Function to wait for service
wait_for_service() {
    local url=$1
    local name=$2
    local max_attempts=30
    local attempt=1
    
    echo -ne "${YELLOW}⏳ Waiting for $name...${NC}"
    
    while [ $attempt -le $max_attempts ]; do
        if curl -s "$url" > /dev/null 2>&1; then
            echo -e "\r${GREEN}✅ $name is ready!${NC}      "
            return 0
        fi
        echo -ne "\r${YELLOW}⏳ Waiting for $name... ($attempt/$max_attempts)${NC}"
        sleep 2
        ((attempt++))
    done
    
    echo -e "\r${RED}❌ $name failed to start${NC}      "
    return 1
}

# Step 1: Check prerequisites
echo -e "${BLUE}📋 Checking prerequisites...${NC}"

if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker not found. Please install Docker first.${NC}"
    exit 1
fi

if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}❌ Docker is not running. Please start Docker.${NC}"
    exit 1
fi

# Step 2: Setup environment
if [ ! -f .env ]; then
    echo -e "${YELLOW}📝 Creating .env file...${NC}"
    cp .env.example .env
    
    # Check if Alpaca keys are needed
    if ! grep -q "ALPACA_API_KEY=." .env; then
        echo -e "${YELLOW}⚠️  Alpaca API keys not configured!${NC}"
        echo "Would you like to:"
        echo "1) Enter Alpaca paper trading credentials now"
        echo "2) Skip (trading features will be disabled)"
        read -p "Choice (1/2): " choice
        
        if [ "$choice" = "1" ]; then
            read -p "Enter Alpaca API Key: " alpaca_key
            read -p "Enter Alpaca Secret Key: " alpaca_secret
            
            # Update .env file
            sed -i "s/ALPACA_API_KEY=/ALPACA_API_KEY=$alpaca_key/" .env
            sed -i "s/ALPACA_API_SECRET=/ALPACA_API_SECRET=$alpaca_secret/" .env
            sed -i "s/ALPACA_KEY_ID=/ALPACA_KEY_ID=$alpaca_key/" .env
            sed -i "s/ALPACA_SECRET_KEY=/ALPACA_SECRET_KEY=$alpaca_secret/" .env
            
            echo -e "${GREEN}✅ Alpaca credentials saved${NC}"
        fi
    fi
fi

# Step 3: Start Docker services
echo -e "${BLUE}🐳 Starting Docker services...${NC}"
docker compose down > /dev/null 2>&1 || true
docker compose up --build -d

# Step 4: Wait for services
wait_for_service "http://localhost:8000/api/health" "API"
wait_for_service "http://localhost:8000/api/health/detailed" "Database"
wait_for_service "http://localhost:9000" "QuestDB"

# Step 5: Auto-create user account
echo -e "${BLUE}👤 Setting up user account...${NC}"

# Check if user wants custom credentials
echo "User account setup:"
echo "1) Use default credentials (email: $DEFAULT_EMAIL)"
echo "2) Enter custom credentials"
read -p "Choice (1/2): " user_choice

if [ "$user_choice" = "2" ]; then
    read -p "Email: " DEFAULT_EMAIL
    read -sp "Password: " DEFAULT_PASSWORD
    echo
    read -p "Full Name: " DEFAULT_NAME
fi

# Register user
echo -e "${YELLOW}Creating user account...${NC}"
REGISTER_RESPONSE=$(curl -s -X POST "http://localhost:8000/api/v1/auth/register" \
    -H "Content-Type: application/json" \
    -d "{
        \"email\": \"$DEFAULT_EMAIL\",
        \"password\": \"$DEFAULT_PASSWORD\",
        \"full_name\": \"$DEFAULT_NAME\"
    }" 2>&1) || true

if echo "$REGISTER_RESPONSE" | grep -q "already registered"; then
    echo -e "${GREEN}✅ User already exists${NC}"
else
    echo -e "${GREEN}✅ User created successfully${NC}"
fi

# Step 6: Get authentication token
echo -e "${YELLOW}🔐 Getting authentication token...${NC}"
LOGIN_RESPONSE=$(curl -s -X POST "http://localhost:8000/api/v1/auth/login" \
    -H "Content-Type: application/json" \
    -d "{
        \"username\": \"$DEFAULT_EMAIL\",
        \"password\": \"$DEFAULT_PASSWORD\"
    }")

TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

if [ -z "$TOKEN" ]; then
    echo -e "${RED}❌ Failed to get authentication token${NC}"
    echo "Response: $LOGIN_RESPONSE"
    exit 1
fi

echo -e "${GREEN}✅ Authentication successful${NC}"

# Save credentials for easy access
cat > .credentials << EOF
# Trademk1 Credentials (auto-generated)
EMAIL=$DEFAULT_EMAIL
PASSWORD=$DEFAULT_PASSWORD
TOKEN=$TOKEN

# Example API calls:
# curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/trading/positions
EOF

echo -e "${GREEN}✅ Credentials saved to .credentials${NC}"

# Step 7: Optional - Create a demo strategy
echo -e "${BLUE}📊 Would you like to create a demo trading strategy? (y/n)${NC}"
read -p "Choice: " create_strategy

if [ "$create_strategy" = "y" ]; then
    echo -e "${YELLOW}Creating SMA Crossover strategy for AAPL...${NC}"
    
    STRATEGY_RESPONSE=$(curl -s -X POST "http://localhost:8000/api/v1/strategies/create" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d '{
            "strategy_type": "sma_crossover",
            "name": "Demo AAPL Strategy",
            "symbols": ["AAPL"],
            "parameters": {
                "fast_period": 10,
                "slow_period": 30,
                "position_size": 0.1
            },
            "allocation": 0.25,
            "enabled": true
        }')
    
    STRATEGY_ID=$(echo "$STRATEGY_RESPONSE" | grep -o '"id":"[^"]*' | cut -d'"' -f4)
    
    if [ ! -z "$STRATEGY_ID" ]; then
        echo -e "${GREEN}✅ Strategy created (ID: $STRATEGY_ID)${NC}"
        echo "STRATEGY_ID=$STRATEGY_ID" >> .credentials
    fi
fi

# Step 8: Display summary
echo
echo -e "${GREEN}🎉 Trademk1 is ready!${NC}"
echo "======================"
echo
echo -e "${BLUE}📚 Quick Reference:${NC}"
echo "• API Docs: http://localhost:8000/api/docs/"
echo "• Health: http://localhost:8000/api/health/detailed"
echo "• QuestDB: http://localhost:9000"
echo
echo -e "${BLUE}🔑 Your Credentials:${NC}"
echo "• Email: $DEFAULT_EMAIL"
echo "• Token saved in: .credentials"
echo
echo -e "${BLUE}📝 Useful Commands:${NC}"
echo "• View logs: docker compose logs -f app"
echo "• Stop services: docker compose down"
echo "• View positions: source .credentials && curl -H \"Authorization: Bearer \$TOKEN\" http://localhost:8000/api/v1/trading/positions"
echo
echo -e "${YELLOW}💡 Next steps:${NC}"
echo "1. Check market data: curl http://localhost:8000/api/v1/market-data/stream_status"
echo "2. Submit trade signals via the API"
echo "3. Monitor your strategies"
echo
echo "Happy trading! 📈"

# Create helper script for easy API access
cat > api.sh << 'EOFSCRIPT'
#!/bin/bash
# Helper script for API calls

source .credentials 2>/dev/null

if [ -z "$TOKEN" ]; then
    echo "No token found. Run ./autostart.sh first"
    exit 1
fi

case "$1" in
    positions)
        curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/trading/positions | jq
        ;;
    orders)
        curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/trading/orders | jq
        ;;
    portfolio)
        curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/portfolio/summary | jq
        ;;
    strategies)
        curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/strategies/list | jq
        ;;
    buy)
        if [ -z "$2" ] || [ -z "$3" ]; then
            echo "Usage: ./api.sh buy SYMBOL QUANTITY"
            exit 1
        fi
        curl -s -X POST "http://localhost:8000/api/v1/trading/signal" \
            -H "Authorization: Bearer $TOKEN" \
            -H "Content-Type: application/json" \
            -d "{\"symbol\": \"$2\", \"side\": \"buy\", \"qty\": $3, \"reason\": \"Manual buy\"}" | jq
        ;;
    sell)
        if [ -z "$2" ] || [ -z "$3" ]; then
            echo "Usage: ./api.sh sell SYMBOL QUANTITY"
            exit 1
        fi
        curl -s -X POST "http://localhost:8000/api/v1/trading/signal" \
            -H "Authorization: Bearer $TOKEN" \
            -H "Content-Type: application/json" \
            -d "{\"symbol\": \"$2\", \"side\": \"sell\", \"qty\": $3, \"reason\": \"Manual sell\"}" | jq
        ;;
    *)
        echo "Trademk1 API Helper"
        echo "==================="
        echo "Usage: ./api.sh [command]"
        echo ""
        echo "Commands:"
        echo "  positions  - Show current positions"
        echo "  orders     - Show recent orders"
        echo "  portfolio  - Show portfolio summary"
        echo "  strategies - List active strategies"
        echo "  buy SYMBOL QTY  - Buy a stock/crypto"
        echo "  sell SYMBOL QTY - Sell a stock/crypto"
        echo ""
        echo "Examples:"
        echo "  ./api.sh positions"
        echo "  ./api.sh buy AAPL 10"
        echo "  ./api.sh sell BTCUSDT 0.1"
        ;;
esac
EOFSCRIPT

chmod +x api.sh

echo -e "${GREEN}✅ Created api.sh helper script${NC}"