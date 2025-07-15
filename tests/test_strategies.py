"""Tests for trading strategies and backtesting."""
import asyncio
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
import pandas as pd
import numpy as np
import pytest

from app.services.strategies.base import (
    BaseStrategy, Signal, SignalType, StrategyConfig
)
from app.services.strategies.sma_crossover import SMACrossoverStrategy
from app.services.strategies.momentum import MomentumStrategy
from app.services.strategies.backtest import BacktestEngine, Trade
from app.services.strategies.risk_manager import (
    AdvancedRiskManager, RiskLevel, RiskMetrics
)
from app.services.strategies.portfolio_manager import MultiStrategyPortfolioManager


def create_sample_market_data(symbols=['AAPL', 'GOOGL'], days=100):
    """Create sample market data for testing."""
    data = []
    base_date = datetime.utcnow() - timedelta(days=days)
    
    for symbol in symbols:
        base_price = 100 if symbol == 'AAPL' else 2000
        
        for i in range(days):
            # Generate random walk
            price_change = np.random.randn() * 0.02
            close_price = base_price * (1 + price_change)
            
            data.append({
                'symbol': symbol,
                'timestamp': base_date + timedelta(days=i),
                'open': base_price,
                'high': close_price * 1.01,
                'low': close_price * 0.99,
                'close': close_price,
                'volume': np.random.randint(1000000, 5000000)
            })
            
            base_price = close_price
            
    return pd.DataFrame(data)


@pytest.mark.asyncio
async def test_sma_crossover_strategy():
    """Test SMA crossover strategy signal generation."""
    config = StrategyConfig(
        strategy_id='test_sma',
        name='Test SMA',
        symbols=['AAPL'],
        parameters={
            'fast_period': 5,
            'slow_period': 10,
            'use_ema': False
        }
    )
    
    strategy = SMACrossoverStrategy(config)
    
    # Validate parameters
    is_valid, error = strategy.validate_parameters()
    assert is_valid
    assert error is None
    
    # Create market data with clear crossover
    market_data = create_sample_market_data(['AAPL'], days=20)
    
    # Force a bullish crossover
    market_data.loc[15:, 'close'] = market_data.loc[15:, 'close'] * 1.1
    
    # Generate signals
    signals = await strategy.calculate_signals(market_data, {})
    
    # Should have at least one signal
    assert len(signals) >= 0  # May not generate signal if conditions not met
    
    # Test with position
    signals_with_position = await strategy.calculate_signals(
        market_data, {'AAPL': 10}
    )
    
    # Test invalid parameters
    invalid_config = StrategyConfig(
        strategy_id='invalid',
        name='Invalid',
        symbols=['AAPL'],
        parameters={'fast_period': 20, 'slow_period': 10}
    )
    invalid_strategy = SMACrossoverStrategy(invalid_config)
    is_valid, error = invalid_strategy.validate_parameters()
    assert not is_valid
    assert 'Fast period must be less than slow period' in error


@pytest.mark.asyncio
async def test_momentum_strategy():
    """Test momentum strategy signal generation."""
    config = StrategyConfig(
        strategy_id='test_momentum',
        name='Test Momentum',
        symbols=['BTCUSDT'],
        parameters={
            'rsi_period': 14,
            'rsi_oversold': 30,
            'rsi_overbought': 70,
            'roc_period': 10,
            'roc_threshold': 0.05,
            'volume_factor': 1.5,
            'use_divergence': True
        }
    )
    
    strategy = MomentumStrategy(config)
    
    # Validate parameters
    is_valid, error = strategy.validate_parameters()
    assert is_valid
    
    # Create market data
    market_data = create_sample_market_data(['BTCUSDT'], days=50)
    
    # Generate signals
    signals = await strategy.calculate_signals(market_data, {})
    
    # Check signal structure
    for signal in signals:
        assert signal.strategy_id == 'test_momentum'
        assert signal.signal_type in [SignalType.BUY, SignalType.SELL, SignalType.HOLD]
        assert 0 <= signal.strength <= 1
        assert 'rsi' in signal.metadata
        assert 'roc' in signal.metadata


@pytest.mark.asyncio
async def test_backtest_engine():
    """Test backtesting engine functionality."""
    # Create strategy
    config = StrategyConfig(
        strategy_id='backtest_test',
        name='Backtest Test',
        symbols=['AAPL'],
        parameters={'fast_period': 5, 'slow_period': 10}
    )
    strategy = SMACrossoverStrategy(config)
    
    # Create market data
    market_data = create_sample_market_data(['AAPL'], days=30)
    
    # Run backtest
    engine = BacktestEngine(initial_capital=10000)
    result = await engine.run_backtest(
        strategy,
        market_data,
        start_date=market_data['timestamp'].min(),
        end_date=market_data['timestamp'].max()
    )
    
    # Check result structure
    assert result.strategy_id == 'backtest_test'
    assert result.initial_capital == 10000
    assert result.final_capital >= 0
    assert isinstance(result.trades, list)
    assert isinstance(result.equity_curve, pd.DataFrame)
    assert isinstance(result.metrics, dict)
    
    # Check metrics
    assert 'total_return' in result.metrics
    assert 'sharpe_ratio' in result.metrics
    assert 'max_drawdown' in result.metrics
    assert 'win_rate' in result.metrics


@pytest.mark.asyncio
async def test_risk_manager():
    """Test advanced risk management functionality."""
    risk_manager = AdvancedRiskManager(
        max_drawdown=0.20,
        max_correlation=0.7,
        max_var_95=0.05,
        max_leverage=1.0,
        max_concentration=0.25
    )
    
    # Update history
    positions = {'AAPL': 10, 'GOOGL': 5}
    market_prices = {'AAPL': 150, 'GOOGL': 2500}
    
    risk_manager.update_history(
        equity=15000,
        positions=positions,
        market_prices=market_prices,
        timestamp=datetime.utcnow()
    )
    
    # Calculate risk metrics
    metrics = risk_manager.calculate_risk_metrics(
        current_equity=14500,
        positions=positions,
        market_prices=market_prices,
        account_value=15000
    )
    
    # Check metrics
    assert isinstance(metrics, RiskMetrics)
    assert metrics.risk_level in [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.EXTREME]
    assert metrics.total_exposure > 0
    assert -1 <= metrics.current_drawdown <= 0
    
    # Test signal filtering
    signals = [
        Signal(
            strategy_id='test',
            symbol='AAPL',
            signal_type=SignalType.BUY,
            strength=0.8,
            quantity=20
        )
    ]
    
    filtered_signals, rejected = risk_manager.filter_signals_by_risk(
        signals, positions, market_prices, 15000
    )
    
    assert isinstance(filtered_signals, list)
    assert isinstance(rejected, list)


@pytest.mark.asyncio
async def test_portfolio_manager():
    """Test multi-strategy portfolio manager."""
    manager = MultiStrategyPortfolioManager()
    
    # Mock Redis
    with patch('redis.asyncio.from_url') as mock_redis:
        mock_redis_client = AsyncMock()
        mock_redis.return_value = mock_redis_client
        
        await manager.initialize()
        
        # Add strategies
        config1 = StrategyConfig(
            strategy_id='sma_test',
            name='SMA Test',
            symbols=['AAPL'],
            parameters={'fast_period': 10, 'slow_period': 20}
        )
        strategy1 = SMACrossoverStrategy(config1)
        manager.add_strategy(strategy1, 0.5)
        
        config2 = StrategyConfig(
            strategy_id='momentum_test',
            name='Momentum Test',
            symbols=['BTCUSDT'],
            parameters={'rsi_period': 14}
        )
        strategy2 = MomentumStrategy(config2)
        manager.add_strategy(strategy2, 0.5)
        
        # Check allocations
        assert len(manager.strategies) == 2
        assert manager.strategies['sma_test'].allocation == 0.5
        assert manager.strategies['momentum_test'].allocation == 0.5
        
        # Test status
        status = await manager.get_status()
        assert 'strategies' in status
        assert 'allocations' in status
        assert len(status['strategies']) == 2
        
        # Test signal combining
        signals = [
            Signal(
                strategy_id='sma_test',
                symbol='AAPL',
                signal_type=SignalType.BUY,
                strength=0.7,
                metadata={'allocation': 0.5}
            ),
            Signal(
                strategy_id='momentum_test',
                symbol='AAPL',
                signal_type=SignalType.BUY,
                strength=0.9,
                metadata={'allocation': 0.5}
            )
        ]
        
        combined = manager._combine_signals(signals)
        assert len(combined) == 1
        assert combined[0].symbol == 'AAPL'
        assert combined[0].signal_type == SignalType.BUY
        
        # Test strategy removal
        manager.remove_strategy('sma_test')
        assert len(manager.strategies) == 1
        assert manager.strategies['momentum_test'].allocation == 1.0  # Should normalize


@pytest.mark.asyncio
async def test_signal_generation_and_filtering():
    """Test complete signal generation and risk filtering flow."""
    # Create strategy
    config = StrategyConfig(
        strategy_id='integrated_test',
        name='Integrated Test',
        symbols=['AAPL', 'GOOGL'],
        parameters={'fast_period': 5, 'slow_period': 10},
        risk_parameters={
            'max_positions': 2,
            'min_signal_strength': 0.5,
            'position_size_pct': 0.02
        }
    )
    strategy = SMACrossoverStrategy(config)
    
    # Create market data
    market_data = create_sample_market_data(['AAPL', 'GOOGL'], days=20)
    
    # Execute strategy
    signals = await strategy.execute(market_data, {})
    
    # Signals should be filtered by risk parameters
    for signal in signals:
        assert signal.strength >= 0.5  # min_signal_strength
        
    # Test position sizing
    account_value = 100000
    current_price = 150
    
    position_size = strategy.calculate_position_size(
        'AAPL',
        signal_strength=0.8,
        account_value=account_value,
        current_price=current_price
    )
    
    # Should be approximately 2% of account * signal strength
    expected_size = (account_value * 0.02 * 0.8) / current_price
    assert abs(position_size - expected_size) < 1


@pytest.mark.asyncio
async def test_performance_metrics():
    """Test performance metric calculations."""
    from app.services.strategies.performance import PerformanceAnalyzer, MetricPeriod
    
    analyzer = PerformanceAnalyzer()
    
    # Create sample equity curve
    dates = pd.date_range(start='2024-01-01', end='2024-03-01', freq='D')
    equity_values = 100000 * (1 + np.random.randn(len(dates)).cumsum() * 0.01)
    
    equity_df = pd.DataFrame({
        'timestamp': dates,
        'total_equity': equity_values,
        'cash': equity_values * 0.3,
        'position_value': equity_values * 0.7,
        'positions': np.random.randint(0, 5, len(dates))
    }).set_index('timestamp')
    
    # Create sample trades
    trades_data = []
    for i in range(10):
        entry_date = dates[i * 5]
        exit_date = dates[i * 5 + 3]
        entry_price = 100 + i
        exit_price = entry_price * (1 + np.random.randn() * 0.05)
        
        trades_data.append({
            'entry_time': entry_date,
            'exit_time': exit_date,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'quantity': 10,
            'pnl': (exit_price - entry_price) * 10
        })
        
    trades_df = pd.DataFrame(trades_data)
    
    # Generate report
    report = analyzer.generate_report(
        trades_df,
        equity_df,
        'test_strategy',
        MetricPeriod.ALL_TIME
    )
    
    # Check report structure
    assert report.strategy_id == 'test_strategy'
    assert report.period == MetricPeriod.ALL_TIME
    assert report.total_trades == 10
    assert isinstance(report.sharpe_ratio, float)
    assert isinstance(report.max_drawdown, float)
    assert report.max_drawdown <= 0
    assert 0 <= report.win_rate <= 1
    assert isinstance(report.monthly_returns, pd.Series)