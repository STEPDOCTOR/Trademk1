#!/bin/bash
# Open the trading bot dashboard

echo "🌐 Opening Trading Bot Dashboard..."
echo "=================================="

# Check if running on different platforms
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Linux
    if command -v xdg-open > /dev/null; then
        xdg-open "http://localhost:8000/dashboard" &
    elif command -v gnome-open > /dev/null; then
        gnome-open "http://localhost:8000/dashboard" &
    else
        echo "Please open http://localhost:8000/dashboard in your browser"
    fi
elif [[ "$OSTYPE" == "darwin"* ]]; then
    # Mac OSX
    open "http://localhost:8000/dashboard" &
elif [[ "$OSTYPE" == "cygwin" ]] || [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "win32" ]]; then
    # Windows
    start "http://localhost:8000/dashboard" &
else
    echo "Please open http://localhost:8000/dashboard in your browser"
fi

echo ""
echo "Dashboard URLs:"
echo "  📊 Desktop: http://localhost:8000/dashboard"
echo "  📱 Mobile:  http://localhost:8000/dashboard/mobile"
echo ""
echo "Make sure the app is running:"
echo "  docker compose up"
echo ""
echo "Performance Check:"
echo "  python3 check_performance.py"