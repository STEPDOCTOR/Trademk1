# Order Management System (OMS) - Trademk1

## Overview
The Order Management System provides paper trading capabilities through Alpaca's paper trading API. It includes:
- Trade signal processing via Redis pub/sub
- Automatic order execution with Alpaca
- Position tracking with real-time P&L
- Risk management with configurable limits
- RESTful API for monitoring and control

## Prerequisites
1. Alpaca paper trading account (free at https://alpaca.markets)
2. Set environment variables in `.env`:
```bash
ALPACA_API_KEY=your_paper_api_key_id
ALPACA_API_SECRET=your_paper_api_secret_key
```

## Starting the OMS

The OMS starts automatically when Docker Compose launches if Alpaca credentials are configured:
```bash
docker compose up --build
```

Watch logs to confirm OMS startup:
```
app_1 | OMS execution engine started
```

## API Endpoints

### Submit Trade Signal
```bash
# Buy 10 shares of Apple
curl -X POST http://localhost:8000/api/v1/trading/signal \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "AAPL",
    "side": "buy",
    "qty": 10,
    "reason": "Technical breakout"
  }'

# Sell 0.1 Bitcoin
curl -X POST http://localhost:8000/api/v1/trading/signal \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSDT",
    "side": "sell",
    "qty": 0.1,
    "reason": "Take profit"
  }'
```

### View Orders
```bash
# Get recent orders
curl http://localhost:8000/api/v1/trading/orders | jq

# Filter by status
curl http://localhost:8000/api/v1/trading/orders?status=filled | jq

# Filter by symbol
curl http://localhost:8000/api/v1/trading/orders?symbol=AAPL | jq

# Get specific order
curl http://localhost:8000/api/v1/trading/orders/{order_id} | jq
```

### View Positions
```bash
# Get open positions
curl http://localhost:8000/api/v1/trading/positions | jq

# Include closed positions
curl http://localhost:8000/api/v1/trading/positions?include_closed=true | jq

# Get portfolio snapshot with P&L
curl http://localhost:8000/api/v1/trading/portfolio | jq
```

## Risk Management

Default limits are configured in the database:
- Max position size: $10,000 USD
- Max crypto order: 1.0 units
- Max stock order: 100 shares

Modify via SQL:
```sql
UPDATE configs SET value = '20000' WHERE key = 'max_position_size_usd';
UPDATE configs SET value = '2.0' WHERE key = 'max_order_qty_crypto';
UPDATE configs SET value = '500' WHERE key = 'max_order_qty_stock';
```

## Order Flow

1. **Signal Submission**: POST to `/api/v1/trading/signal`
2. **Redis Queue**: Signal published to `trade_signals` channel
3. **Execution Engine**: 
   - Validates market hours (stocks only)
   - Checks risk limits
   - Submits to Alpaca
4. **Order Updates**: Alpaca WebSocket updates order status
5. **Position Updates**: Fills trigger position and P&L calculations
6. **Price Updates**: QuestDB prices update unrealized P&L every 5 seconds

## Error Handling

Orders can be rejected for:
- Market closed (stocks outside 9:30 AM - 4:00 PM ET)
- Exceeds quantity limits
- Exceeds position size limit
- Alpaca API errors

Check rejected orders:
```bash
curl http://localhost:8000/api/v1/trading/orders?status=rejected | jq
```

## Database Schema

### Orders Table
- `id`: UUID primary key
- `symbol`: Trading symbol
- `side`: buy/sell
- `qty`: Order quantity
- `type`: market/limit
- `status`: pending/submitted/filled/rejected/cancelled
- `alpaca_id`: Alpaca order ID
- `filled_price`: Average fill price
- `reason`: Signal reason
- `error_message`: Rejection reason

### Positions Table
- `id`: UUID primary key
- `symbol`: Trading symbol (unique)
- `qty`: Current position size
- `avg_price`: Average entry price
- `unrealized_pnl`: Current P&L
- `realized_pnl`: Closed P&L
- `last_price`: Latest market price
- `market_value`: Position value

## Testing

Run OMS tests:
```bash
docker compose exec app pytest tests/test_oms.py -v
```

Test signal processing without Alpaca:
```bash
# Start with mock mode
ALPACA_API_KEY=mock docker compose up
```

## Monitoring

Check OMS health:
```bash
# Execution engine runs as background task
curl http://localhost:8000/api/health/detailed | jq '.execution_engine_status'

# Check Redis connectivity
docker compose exec redis redis-cli ping

# Monitor signal queue
docker compose exec redis redis-cli subscribe trade_signals
```

## Troubleshooting

### OMS not starting
- Check Alpaca credentials in `.env`
- Verify Redis is running: `docker compose ps redis`
- Check logs: `docker compose logs app | grep -i oms`

### Orders not executing
- Verify market hours for stocks
- Check order status for errors
- Review app logs for Alpaca API errors

### Position P&L not updating
- Ensure market data ingestion is running
- Check QuestDB has recent ticks: `http://localhost:9000`
- Verify position manager background task

## Production Considerations

1. **API Keys**: Use separate keys for dev/prod
2. **Risk Limits**: Adjust based on account size
3. **Monitoring**: Add alerts for failed orders
4. **Backup**: Regular position/order snapshots
5. **Rate Limits**: Alpaca allows 200 requests/minute