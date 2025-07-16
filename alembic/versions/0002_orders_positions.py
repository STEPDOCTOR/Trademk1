"""Add orders and positions tables

Revision ID: 0002_orders_positions
Revises: 0001_initial
Create Date: 2025-07-15

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0002_orders_positions'
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create orders table
    op.create_table('orders',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('side', sa.Enum('buy', 'sell', name='orderside'), nullable=False),
        sa.Column('qty', sa.Float(), nullable=False),
        sa.Column('type', sa.Enum('market', 'limit', 'stop', 'stop_limit', name='ordertype'), nullable=False),
        sa.Column('status', sa.Enum('pending', 'submitted', 'partial', 'filled', 'cancelled', 'rejected', 'expired', name='orderstatus'), nullable=False),
        sa.Column('price', sa.Float(), nullable=True),
        sa.Column('stop_price', sa.Float(), nullable=True),
        sa.Column('filled_price', sa.Float(), nullable=True),
        sa.Column('alpaca_id', sa.String(length=100), nullable=True),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('filled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reason', sa.String(length=500), nullable=True),
        sa.Column('error_message', sa.String(length=500), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_orders_alpaca_id'), 'orders', ['alpaca_id'], unique=True)
    op.create_index(op.f('ix_orders_status'), 'orders', ['status'], unique=False)
    op.create_index(op.f('ix_orders_symbol'), 'orders', ['symbol'], unique=False)
    
    # Create positions table
    op.create_table('positions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('qty', sa.Float(), nullable=False),
        sa.Column('avg_price', sa.Float(), nullable=False),
        sa.Column('unrealized_pnl', sa.Float(), nullable=False),
        sa.Column('realized_pnl', sa.Float(), nullable=False),
        sa.Column('last_price', sa.Float(), nullable=True),
        sa.Column('last_price_updated', sa.DateTime(timezone=True), nullable=True),
        sa.Column('market_value', sa.Float(), nullable=False),
        sa.Column('cost_basis', sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_positions_symbol'), 'positions', ['symbol'], unique=True)
    
    # Create trigger for orders table
    op.execute("""
        CREATE TRIGGER update_orders_updated_at
        BEFORE UPDATE ON orders
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at();
    """)
    
    # Create trigger for positions table
    op.execute("""
        CREATE TRIGGER update_positions_updated_at
        BEFORE UPDATE ON positions
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at();
    """)
    
    # Add risk management configs
    op.execute("""
        INSERT INTO configs (id, key, value, scope, description, created_at, updated_at)
        VALUES 
        (gen_random_uuid(), 'max_position_size_usd', '10000', 'risk', 'Maximum USD value per position', NOW(), NOW()),
        (gen_random_uuid(), 'max_order_qty_crypto', '1.0', 'risk', 'Maximum quantity per crypto order', NOW(), NOW()),
        (gen_random_uuid(), 'max_order_qty_stock', '100', 'risk', 'Maximum quantity per stock order', NOW(), NOW())
        ON CONFLICT (key) DO NOTHING;
    """)


def downgrade() -> None:
    # Drop triggers
    op.execute('DROP TRIGGER IF EXISTS update_orders_updated_at ON orders')
    op.execute('DROP TRIGGER IF EXISTS update_positions_updated_at ON positions')
    
    # Drop indexes
    op.drop_index(op.f('ix_positions_symbol'), table_name='positions')
    op.drop_index(op.f('ix_orders_symbol'), table_name='orders')
    op.drop_index(op.f('ix_orders_status'), table_name='orders')
    op.drop_index(op.f('ix_orders_alpaca_id'), table_name='orders')
    
    # Drop tables
    op.drop_table('positions')
    op.drop_table('orders')
    
    # Drop enums
    op.execute('DROP TYPE IF EXISTS orderstatus')
    op.execute('DROP TYPE IF EXISTS ordertype')
    op.execute('DROP TYPE IF EXISTS orderside')
    
    # Remove risk configs
    op.execute("""
        DELETE FROM configs 
        WHERE key IN ('max_position_size_usd', 'max_order_qty_crypto', 'max_order_qty_stock')
    """)