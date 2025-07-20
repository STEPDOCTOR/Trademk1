#!/usr/bin/env python3
"""Configure daily limits for the aggressive trading bot."""
import requests
import json

print("⚙️  Configuring Daily Limits for Aggressive Bot")
print("="*50)

# Configuration options
configs = [
    {
        "name": "Conservative",
        "loss_limit": -500,
        "profit_target": 1000,
        "stop_on_loss": True,
        "stop_on_profit": False
    },
    {
        "name": "Moderate",
        "loss_limit": -1000,
        "profit_target": 2000,
        "stop_on_loss": True,
        "stop_on_profit": False
    },
    {
        "name": "Aggressive",
        "loss_limit": -2000,
        "profit_target": 5000,
        "stop_on_loss": True,
        "stop_on_profit": False
    },
    {
        "name": "Custom",
        "loss_limit": None,
        "profit_target": None,
        "stop_on_loss": True,
        "stop_on_profit": False
    }
]

# Display options
print("Select a daily limit configuration:")
for i, config in enumerate(configs):
    if config["loss_limit"]:
        print(f"{i+1}. {config['name']} - Loss: ${abs(config['loss_limit'])}, Target: ${config['profit_target']}")
    else:
        print(f"{i+1}. {config['name']} - Set your own limits")

# Get user choice
try:
    choice = int(input("\nSelect option (1-4): ")) - 1
    if choice < 0 or choice >= len(configs):
        print("Invalid choice")
        exit(1)
except ValueError:
    print("Invalid input")
    exit(1)

selected = configs[choice]

# Handle custom configuration
if selected["name"] == "Custom":
    try:
        loss_limit = -abs(float(input("Enter daily loss limit in dollars (e.g., 1000): ")))
        profit_target = abs(float(input("Enter daily profit target in dollars (e.g., 2000): ")))
        stop_on_loss = input("Stop trading when loss limit hit? (y/n): ").lower() == 'y'
        stop_on_profit = input("Stop trading when profit target hit? (y/n): ").lower() == 'y'
        
        selected["loss_limit"] = loss_limit
        selected["profit_target"] = profit_target
        selected["stop_on_loss"] = stop_on_loss
        selected["stop_on_profit"] = stop_on_profit
    except ValueError:
        print("Invalid input")
        exit(1)

print(f"\nConfiguring {selected['name']} limits:")
print(f"  • Daily Loss Limit: ${abs(selected['loss_limit'])}")
print(f"  • Daily Profit Target: ${selected['profit_target']}")
print(f"  • Stop on Loss: {'Yes' if selected['stop_on_loss'] else 'No'}")
print(f"  • Stop on Profit: {'Yes' if selected['stop_on_profit'] else 'No'}")

# Note: Since we're modifying the bot directly, we'll need to restart it
print("\n⚠️  Note: Bot will need to be restarted for changes to take effect")
print("   Run: docker compose restart app")

# Save configuration to a file that the bot can read
config_data = {
    "daily_limits": {
        "enabled": True,
        "loss_limit": selected["loss_limit"],
        "profit_target": selected["profit_target"], 
        "stop_on_loss": selected["stop_on_loss"],
        "stop_on_profit": selected["stop_on_profit"]
    }
}

with open("daily_limits_config.json", "w") as f:
    json.dump(config_data, f, indent=2)
    
print(f"\n✅ Configuration saved to daily_limits_config.json")
print("\nTo apply changes:")
print("1. docker compose restart app")
print("2. python3 ACTIVATE_BOT.py")
print("\nMonitor performance with:")
print("  python3 check_performance.py")