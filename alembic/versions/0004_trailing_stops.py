"""Add trailing stops table

Revision ID: 0004_trailing_stops
Revises: 0003_performance_tracking
Create Date: 2024-01-20 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0004_trailing_stops'
down_revision = '0003_performance_tracking'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create trailing_stops table
    op.create_table('trailing_stops',
        sa.Column('id', postgresql.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('symbol', sa.String(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=True),
        sa.Column('trail_percent', sa.Float(), nullable=False),
        sa.Column('trail_amount', sa.Float(), nullable=True),
        sa.Column('initial_price', sa.Float(), nullable=False),
        sa.Column('highest_price', sa.Float(), nullable=False),
        sa.Column('stop_price', sa.Float(), nullable=False),
        sa.Column('last_updated', sa.DateTime(timezone=True), nullable=True),
        sa.Column('times_adjusted', sa.Float(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('triggered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('triggered_price', sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('symbol')
    )
    op.create_index(op.f('ix_trailing_stops_symbol'), 'trailing_stops', ['symbol'], unique=True)
    
    # Add trigger for updated_at
    op.execute("""
        CREATE TRIGGER update_trailing_stops_updated_at BEFORE UPDATE ON trailing_stops
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)


def downgrade() -> None:
    op.drop_index(op.f('ix_trailing_stops_symbol'), table_name='trailing_stops')
    op.drop_table('trailing_stops')