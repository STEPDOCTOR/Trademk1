# Trading Strategy Framework - Trademk1

## Overview

The Trading Strategy Framework provides a complete system for developing, backtesting, and deploying automated trading strategies. It includes:

- **Base Strategy Framework**: Abstract base class for all strategies
- **Example Strategies**: SMA Crossover and Momentum strategies
- **Backtesting Engine**: Historical performance simulation
- **Risk Management**: Advanced drawdown and correlation controls
- **Portfolio Manager**: Multi-strategy allocation and rebalancing
- **Performance Analytics**: Comprehensive metrics and reporting

## Architecture

```
app/services/strategies/
├── base.py              # Abstract base strategy class
├── sma_crossover.py     # Simple Moving Average crossover strategy
├── momentum.py          # RSI and momentum-based strategy
├── backtest.py          # Backtesting engine
├── risk_manager.py      # Advanced risk management
├── portfolio_manager.py # Multi-strategy portfolio management
├── performance.py       # Performance metrics and reporting
└── config_manager.py    # Database configuration management
```

## Creating a New Strategy

### 1. Inherit from BaseStrategy

```python
from app.services.strategies.base import BaseStrategy, Signal, SignalType

class MyStrategy(BaseStrategy):
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        # Initialize strategy-specific parameters
        
    async def calculate_signals(
        self, 
        market_data: pd.DataFrame,
        current_positions: Dict[str, float]
    ) -> List[Signal]:
        # Implement your trading logic
        signals = []
        
        # Generate buy/sell signals
        if buy_condition:
            signal = Signal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                signal_type=SignalType.BUY,
                strength=0.8,  # 0-1 confidence
                reason="Buy condition met"
            )
            signals.append(signal)
            
        return signals
        
    def validate_parameters(self) -> Tuple[bool, Optional[str]]:
        # Validate strategy parameters
        if self.parameters.get('period', 0) <= 0:
            return False, "Period must be positive"
        return True, None
```

### 2. Strategy Configuration

```python
config = StrategyConfig(
    strategy_id='my_strategy_001',
    name='My Custom Strategy',
    symbols=['AAPL', 'GOOGL', 'BTCUSDT'],
    parameters={
        'period': 20,
        'threshold': 0.02,
        'use_volume': True
    },
    risk_parameters={
        'max_positions': 3,
        'position_size_pct': 0.02,
        'min_signal_strength': 0.5
    }
)
```

## Using the Strategy API

### Create a Strategy

```bash
curl -X POST http://localhost:8000/api/v1/strategies/create \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_type": "sma_crossover",
    "name": "BTC SMA Strategy",
    "symbols": ["BTCUSDT"],
    "parameters": {
      "fast_period": 10,
      "slow_period": 30
    },
    "allocation": 0.25
  }'
```

### List Strategies

```bash
curl http://localhost:8000/api/v1/strategies/list | jq
```

### Run Backtest

```bash
curl -X POST http://localhost:8000/api/v1/strategies/backtest \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_id": "sma_btc_20241215_120000",
    "start_date": "2024-01-01T00:00:00",
    "end_date": "2024-12-01T00:00:00",
    "initial_capital": 100000
  }'
```

### Get Performance

```bash
curl http://localhost:8000/api/v1/strategies/performance/sma_btc_20241215_120000?period=monthly | jq
```

### Check Portfolio Risk

```bash
curl http://localhost:8000/api/v1/strategies/portfolio/risk | jq
```

## Backtesting

### Running a Backtest

```python
from app.services.strategies.backtest import BacktestEngine

# Create engine
engine = BacktestEngine(
    initial_capital=100000,
    commission=0.001,  # 0.1%
    slippage=0.0005    # 0.05%
)

# Run backtest
result = await engine.run_backtest(
    strategy=my_strategy,
    market_data=historical_data,
    start_date=datetime(2024, 1, 1),
    end_date=datetime(2024, 12, 1)
)

# Access results
print(f"Total Return: {result.metrics['total_return']:.2%}")
print(f"Sharpe Ratio: {result.metrics['sharpe_ratio']:.2f}")
print(f"Max Drawdown: {result.metrics['max_drawdown']:.2%}")
print(f"Win Rate: {result.metrics['win_rate']:.2%}")
```

### Backtest Metrics

- **Returns**: Total, annualized, volatility
- **Risk-Adjusted**: Sharpe, Sortino, Calmar ratios
- **Drawdown**: Maximum, duration, recovery
- **Trade Stats**: Win rate, profit factor, expectancy
- **VaR/CVaR**: Value at Risk metrics

## Risk Management

### Risk Levels

- **LOW**: Normal operation
- **MEDIUM**: Caution, reduced position sizes
- **HIGH**: High risk, minimal new positions
- **EXTREME**: Emergency mode, close positions only

### Risk Parameters

```python
risk_manager = AdvancedRiskManager(
    max_drawdown=0.20,      # 20% maximum drawdown
    max_correlation=0.7,    # Maximum position correlation
    max_var_95=0.05,        # 5% Value at Risk limit
    max_leverage=1.0,       # No leverage
    max_concentration=0.25  # 25% max in single position
)
```

### Risk Monitoring

The system continuously monitors:
- Portfolio drawdown
- Position correlations
- Value at Risk (VaR)
- Concentration risk
- Leverage ratios

## Multi-Strategy Portfolio

### Portfolio Allocation

Strategies are allocated based on:
1. **Performance Score**: Historical win rate and returns
2. **Risk Contribution**: Impact on portfolio risk
3. **Correlation**: Diversification benefits

### Dynamic Rebalancing

The portfolio manager automatically:
- Rebalances allocations weekly
- Adjusts for strategy performance
- Maintains risk limits
- Disables strategies in extreme risk

### Adding Strategies to Portfolio

```python
# Create portfolio manager
portfolio = MultiStrategyPortfolioManager()

# Add strategies
portfolio.add_strategy(sma_strategy, allocation=0.4)
portfolio.add_strategy(momentum_strategy, allocation=0.3)
portfolio.add_strategy(mean_reversion_strategy, allocation=0.3)

# Start portfolio management
await portfolio.run()
```

## Performance Reporting

### Generate Performance Report

```python
analyzer = PerformanceAnalyzer()

report = analyzer.generate_report(
    trades=trade_history,
    equity_curve=equity_data,
    strategy_id='my_strategy',
    period=MetricPeriod.MONTHLY
)

# Access metrics
print(f"Monthly Sharpe: {report.sharpe_ratio:.2f}")
print(f"Win Rate: {report.win_rate:.2%}")
print(f"Avg Trade Duration: {report.avg_trade_duration:.1f} days")
```

### Performance Metrics

**Return Metrics**
- Total and annualized returns
- Monthly/quarterly returns
- Rolling performance

**Risk Metrics**
- Volatility and downside deviation
- Maximum drawdown and duration
- VaR and CVaR (Expected Shortfall)

**Trade Metrics**
- Win rate and profit factor
- Average win/loss
- Trade duration statistics
- Time in market

## Strategy Examples

### SMA Crossover Strategy

**Parameters:**
- `fast_period`: Fast moving average period (default: 10)
- `slow_period`: Slow moving average period (default: 30)
- `use_ema`: Use exponential MA instead of simple (default: false)

**Signals:**
- BUY: Fast MA crosses above slow MA
- SELL: Fast MA crosses below slow MA

### Momentum Strategy

**Parameters:**
- `rsi_period`: RSI calculation period (default: 14)
- `rsi_oversold`: Oversold threshold (default: 30)
- `rsi_overbought`: Overbought threshold (default: 70)
- `roc_period`: Rate of change period (default: 10)
- `use_divergence`: Check price/RSI divergence (default: true)

**Signals:**
- BUY: RSI oversold + positive momentum + volume
- SELL: RSI overbought or momentum reversal

## Database Configuration

Strategies can be stored and loaded from the database:

```sql
-- View configured strategies
SELECT strategy_id, name, strategy_type, allocation, performance_score
FROM strategy_configs
WHERE enabled = true;

-- Update allocation
UPDATE strategy_configs 
SET allocation = 0.3 
WHERE strategy_id = 'momentum_multi_default';
```

## Testing Strategies

Run strategy tests:
```bash
docker compose exec app pytest tests/test_strategies.py -v
```

Test coverage includes:
- Signal generation
- Parameter validation
- Backtesting accuracy
- Risk management
- Portfolio allocation

## Best Practices

### Strategy Development

1. **Start Simple**: Begin with basic logic, add complexity gradually
2. **Validate Parameters**: Always implement parameter validation
3. **Handle Edge Cases**: Check for insufficient data, missing prices
4. **Document Logic**: Clear comments on signal conditions
5. **Test Thoroughly**: Backtest over different market conditions

### Risk Management

1. **Set Conservative Limits**: Start with tight risk controls
2. **Monitor Correlations**: Avoid concentrated bets
3. **Use Stop Losses**: Implement in strategy logic
4. **Regular Rebalancing**: Don't let winners run too long
5. **Emergency Stops**: Have manual override capability

### Performance Optimization

1. **Vectorize Calculations**: Use pandas/numpy operations
2. **Cache Indicators**: Avoid recalculating static values
3. **Batch Operations**: Process multiple symbols together
4. **Async Processing**: Use async for I/O operations
5. **Profile Code**: Identify and optimize bottlenecks

## Troubleshooting

### Strategy Not Generating Signals

1. Check market data availability
2. Verify parameter values
3. Review signal conditions
4. Check risk filters
5. Enable debug logging

### Poor Backtest Performance

1. Review transaction costs
2. Check for look-ahead bias
3. Verify data quality
4. Adjust parameters
5. Consider market regime

### High Drawdowns

1. Reduce position sizes
2. Tighten risk limits
3. Add stop losses
4. Improve entry timing
5. Diversify strategies

## Future Enhancements

- Machine learning strategies
- Options strategies support
- Pairs trading framework
- Market regime detection
- Real-time optimization
- Cloud-based backtesting
- Strategy marketplace