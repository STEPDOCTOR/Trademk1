"""Add performance tracking tables

Revision ID: 0003_performance_tracking
Revises: 0002_orders_positions
Create Date: 2024-01-20 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0003_performance_tracking'
down_revision = '0002_orders_positions'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create trade_history table
    op.create_table('trade_history',
        sa.Column('id', postgresql.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('symbol', sa.String(), nullable=False),
        sa.Column('trade_type', sa.Enum('BUY', 'SELL', name='tradetype'), nullable=False),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('price', sa.Float(), nullable=False),
        sa.Column('total_value', sa.Float(), nullable=False),
        sa.Column('executed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('alpaca_order_id', sa.String(), nullable=True),
        sa.Column('reason', sa.Enum('MOMENTUM', 'STOP_LOSS', 'TAKE_PROFIT', 'REBALANCE', 'MANUAL', 'TRAILING_STOP', 'DAILY_TARGET', name='tradereason'), nullable=False),
        sa.Column('strategy_name', sa.String(), nullable=True),
        sa.Column('entry_price', sa.Float(), nullable=True),
        sa.Column('exit_price', sa.Float(), nullable=True),
        sa.Column('profit_loss', sa.Float(), nullable=True),
        sa.Column('profit_loss_pct', sa.Float(), nullable=True),
        sa.Column('market_conditions', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('position_size_before', sa.Float(), nullable=True),
        sa.Column('position_size_after', sa.Float(), nullable=True),
        sa.Column('portfolio_value_at_trade', sa.Float(), nullable=True),
        sa.Column('stop_loss_price', sa.Float(), nullable=True),
        sa.Column('take_profit_price', sa.Float(), nullable=True),
        sa.Column('risk_amount', sa.Float(), nullable=True),
        sa.Column('trading_day', sa.DateTime(timezone=True), nullable=True),
        sa.Column('daily_trade_number', sa.Integer(), nullable=True),
        sa.Column('user_id', postgresql.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_trade_history_alpaca_order_id'), 'trade_history', ['alpaca_order_id'], unique=False)
    op.create_index(op.f('ix_trade_history_symbol'), 'trade_history', ['symbol'], unique=False)
    op.create_index(op.f('ix_trade_history_trading_day'), 'trade_history', ['trading_day'], unique=False)
    
    # Create daily_performance table
    op.create_table('daily_performance',
        sa.Column('id', postgresql.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('trading_date', sa.Date(), nullable=False),
        sa.Column('total_trades', sa.Integer(), nullable=True),
        sa.Column('winning_trades', sa.Integer(), nullable=True),
        sa.Column('losing_trades', sa.Integer(), nullable=True),
        sa.Column('win_rate', sa.Float(), nullable=True),
        sa.Column('total_profit_loss', sa.Float(), nullable=True),
        sa.Column('total_profit_loss_pct', sa.Float(), nullable=True),
        sa.Column('best_trade', sa.Float(), nullable=True),
        sa.Column('worst_trade', sa.Float(), nullable=True),
        sa.Column('average_win', sa.Float(), nullable=True),
        sa.Column('average_loss', sa.Float(), nullable=True),
        sa.Column('total_volume_traded', sa.Float(), nullable=True),
        sa.Column('total_commission', sa.Float(), nullable=True),
        sa.Column('starting_balance', sa.Float(), nullable=True),
        sa.Column('ending_balance', sa.Float(), nullable=True),
        sa.Column('high_water_mark', sa.Float(), nullable=True),
        sa.Column('max_drawdown', sa.Float(), nullable=True),
        sa.Column('max_drawdown_pct', sa.Float(), nullable=True),
        sa.Column('sharpe_ratio', sa.Float(), nullable=True),
        sa.Column('sortino_ratio', sa.Float(), nullable=True),
        sa.Column('profit_factor', sa.Float(), nullable=True),
        sa.Column('positions_opened', sa.Integer(), nullable=True),
        sa.Column('positions_closed', sa.Integer(), nullable=True),
        sa.Column('max_positions_held', sa.Integer(), nullable=True),
        sa.Column('average_position_size', sa.Float(), nullable=True),
        sa.Column('trades_by_strategy', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('pnl_by_strategy', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('market_volatility', sa.Float(), nullable=True),
        sa.Column('market_trend', sa.String(), nullable=True),
        sa.Column('daily_loss_limit_hit', sa.DateTime(timezone=True), nullable=True),
        sa.Column('daily_profit_target_hit', sa.DateTime(timezone=True), nullable=True),
        sa.Column('user_id', postgresql.UUID(), nullable=True),
        sa.Column('calculated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_daily_performance_trading_date'), 'daily_performance', ['trading_date'], unique=False)
    
    # Create realtime_metrics table
    op.create_table('realtime_metrics',
        sa.Column('id', postgresql.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('session_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_updated', sa.DateTime(timezone=True), nullable=True),
        sa.Column('unrealized_pnl', sa.Float(), nullable=True),
        sa.Column('realized_pnl', sa.Float(), nullable=True),
        sa.Column('total_pnl', sa.Float(), nullable=True),
        sa.Column('total_pnl_pct', sa.Float(), nullable=True),
        sa.Column('open_positions', sa.Integer(), nullable=True),
        sa.Column('total_position_value', sa.Float(), nullable=True),
        sa.Column('cash_available', sa.Float(), nullable=True),
        sa.Column('buying_power', sa.Float(), nullable=True),
        sa.Column('trades_today', sa.Integer(), nullable=True),
        sa.Column('winning_trades_today', sa.Integer(), nullable=True),
        sa.Column('losing_trades_today', sa.Integer(), nullable=True),
        sa.Column('volume_today', sa.Float(), nullable=True),
        sa.Column('current_risk_exposure', sa.Float(), nullable=True),
        sa.Column('risk_exposure_pct', sa.Float(), nullable=True),
        sa.Column('largest_position_pct', sa.Float(), nullable=True),
        sa.Column('approaching_daily_loss_limit', sa.Float(), nullable=True),
        sa.Column('approaching_position_limit', sa.Integer(), nullable=True),
        sa.Column('active_strategies', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('pending_signals', sa.Integer(), nullable=True),
        sa.Column('market_status', sa.String(), nullable=True),
        sa.Column('next_market_open', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_market_close', sa.DateTime(timezone=True), nullable=True),
        sa.Column('user_id', postgresql.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Add triggers for updated_at
    op.execute("""
        CREATE TRIGGER update_trade_history_updated_at BEFORE UPDATE ON trade_history
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        
        CREATE TRIGGER update_daily_performance_updated_at BEFORE UPDATE ON daily_performance
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        
        CREATE TRIGGER update_realtime_metrics_updated_at BEFORE UPDATE ON realtime_metrics
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)


def downgrade() -> None:
    op.drop_table('realtime_metrics')
    op.drop_table('daily_performance')
    op.drop_index(op.f('ix_trade_history_trading_day'), table_name='trade_history')
    op.drop_index(op.f('ix_trade_history_symbol'), table_name='trade_history')
    op.drop_index(op.f('ix_trade_history_alpaca_order_id'), table_name='trade_history')
    op.drop_table('trade_history')
    
    # Drop enums
    op.execute("DROP TYPE IF EXISTS tradetype")
    op.execute("DROP TYPE IF EXISTS tradereason")