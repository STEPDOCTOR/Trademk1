"""Add strategy configurations table

Revision ID: 0003_strategy_configs
Revises: 0002_orders_positions
Create Date: 2025-07-15

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0003_strategy_configs'
down_revision = '0002_orders_positions'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create strategy_configs table
    op.create_table('strategy_configs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('strategy_id', sa.String(length=100), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('strategy_type', sa.String(length=50), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('symbols', sa.JSON(), nullable=False),
        sa.Column('parameters', sa.JSON(), nullable=False),
        sa.Column('risk_parameters', sa.JSON(), nullable=False),
        sa.Column('allocation', sa.Float(), nullable=False),
        sa.Column('performance_score', sa.Float(), nullable=False),
        sa.Column('last_signal_time', sa.String(length=50), nullable=True),
        sa.Column('total_signals', sa.String(length=10), nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_strategy_configs_strategy_id'), 'strategy_configs', ['strategy_id'], unique=True)
    
    # Create trigger for strategy_configs table
    op.execute("""
        CREATE TRIGGER update_strategy_configs_updated_at
        BEFORE UPDATE ON strategy_configs
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column();
    """)
    
    # Add default strategy configurations
    op.execute("""
        INSERT INTO strategy_configs (id, strategy_id, name, strategy_type, enabled, symbols, parameters, risk_parameters, allocation, performance_score, total_signals, metadata_json, created_at, updated_at)
        VALUES 
        (gen_random_uuid(), 'sma_btc_default', 'BTC SMA Crossover', 'sma_crossover', true, 
         '["BTCUSDT"]'::json, 
         '{"fast_period": 10, "slow_period": 30, "use_ema": false}'::json,
         '{"max_positions": 1, "min_signal_strength": 0.3, "position_size_pct": 0.02}'::json,
         0.25, 0.5, '0', '{}'::json, NOW(), NOW()),
         
        (gen_random_uuid(), 'momentum_multi_default', 'Multi-Asset Momentum', 'momentum', true,
         '["AAPL", "GOOGL", "MSFT"]'::json,
         '{"rsi_period": 14, "rsi_oversold": 30, "rsi_overbought": 70, "roc_period": 10, "roc_threshold": 0.05}'::json,
         '{"max_positions": 3, "min_signal_strength": 0.4, "position_size_pct": 0.015}'::json,
         0.25, 0.5, '0', '{}'::json, NOW(), NOW())
    """)


def downgrade() -> None:
    # Drop trigger
    op.execute('DROP TRIGGER IF EXISTS update_strategy_configs_updated_at ON strategy_configs')
    
    # Drop indexes
    op.drop_index(op.f('ix_strategy_configs_strategy_id'), table_name='strategy_configs')
    
    # Drop table
    op.drop_table('strategy_configs')