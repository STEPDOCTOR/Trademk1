"""Add user enhancements and related tables

Revision ID: 0004_user_enhancements
Revises: 0003_strategy_configs
Create Date: 2025-07-15

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0004_user_enhancements'
down_revision = '0003_strategy_configs'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Update users table
    op.add_column('users', sa.Column('full_name', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('phone_number', sa.String(length=50), nullable=True))
    op.add_column('users', sa.Column('is_verified', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('users', sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('max_daily_trades', sa.String(length=10), nullable=False, server_default='100'))
    op.add_column('users', sa.Column('max_position_size', sa.String(length=20), nullable=False, server_default='10000'))
    
    # Create api_keys table
    op.create_table('api_keys',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('key_hash', sa.String(length=255), nullable=False),
        sa.Column('scopes', sa.String(length=500), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rate_limit_per_minute', sa.String(length=10), nullable=False),
        sa.Column('rate_limit_per_hour', sa.String(length=10), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('allowed_ips', sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_api_keys_key_hash'), 'api_keys', ['key_hash'], unique=True)
    
    # Create user_portfolios table
    op.create_table('user_portfolios',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('total_value', sa.Float(), nullable=False),
        sa.Column('cash_balance', sa.Float(), nullable=False),
        sa.Column('positions_value', sa.Float(), nullable=False),
        sa.Column('total_pnl', sa.Float(), nullable=False),
        sa.Column('total_pnl_percent', sa.Float(), nullable=False),
        sa.Column('daily_pnl', sa.Float(), nullable=False),
        sa.Column('daily_pnl_percent', sa.Float(), nullable=False),
        sa.Column('current_drawdown', sa.Float(), nullable=False),
        sa.Column('max_drawdown', sa.Float(), nullable=False),
        sa.Column('sharpe_ratio', sa.Float(), nullable=False),
        sa.Column('win_rate', sa.Float(), nullable=False),
        sa.Column('total_trades', sa.String(length=10), nullable=False),
        sa.Column('winning_trades', sa.String(length=10), nullable=False),
        sa.Column('losing_trades', sa.String(length=10), nullable=False),
        sa.Column('active_positions', sa.String(length=10), nullable=False),
        sa.Column('strategy_allocations', sa.JSON(), nullable=False),
        sa.Column('last_calculated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )
    
    # Create user_preferences table
    op.create_table('user_preferences',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('default_order_type', sa.String(length=20), nullable=False),
        sa.Column('default_time_in_force', sa.String(length=20), nullable=False),
        sa.Column('risk_level', sa.String(length=20), nullable=False),
        sa.Column('email_notifications', sa.Boolean(), nullable=False),
        sa.Column('push_notifications', sa.Boolean(), nullable=False),
        sa.Column('sms_notifications', sa.Boolean(), nullable=False),
        sa.Column('notify_on_fill', sa.Boolean(), nullable=False),
        sa.Column('notify_on_rejection', sa.Boolean(), nullable=False),
        sa.Column('notify_on_high_risk', sa.Boolean(), nullable=False),
        sa.Column('notify_daily_summary', sa.Boolean(), nullable=False),
        sa.Column('theme', sa.String(length=20), nullable=False),
        sa.Column('timezone', sa.String(length=50), nullable=False),
        sa.Column('language', sa.String(length=10), nullable=False),
        sa.Column('currency', sa.String(length=10), nullable=False),
        sa.Column('default_chart_interval', sa.String(length=10), nullable=False),
        sa.Column('default_market_view', sa.String(length=20), nullable=False),
        sa.Column('advanced_mode', sa.Boolean(), nullable=False),
        sa.Column('beta_features', sa.Boolean(), nullable=False),
        sa.Column('custom_settings', sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )
    
    # Create audit_logs table
    op.create_table('audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.String(length=500), nullable=True),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('event_category', sa.String(length=50), nullable=False),
        sa.Column('event_severity', sa.String(length=20), nullable=False),
        sa.Column('resource_type', sa.String(length=50), nullable=True),
        sa.Column('resource_id', sa.String(length=100), nullable=True),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('request_method', sa.String(length=10), nullable=True),
        sa.Column('request_path', sa.String(length=500), nullable=True),
        sa.Column('request_data', sa.JSON(), nullable=True),
        sa.Column('response_status', sa.String(length=3), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_audit_event_time', 'audit_logs', ['event_type', 'created_at'], unique=False)
    op.create_index('idx_audit_resource', 'audit_logs', ['resource_type', 'resource_id'], unique=False)
    op.create_index('idx_audit_user_time', 'audit_logs', ['user_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_audit_logs_event_category'), 'audit_logs', ['event_category'], unique=False)
    op.create_index(op.f('ix_audit_logs_event_type'), 'audit_logs', ['event_type'], unique=False)
    op.create_index(op.f('ix_audit_logs_resource_type'), 'audit_logs', ['resource_type'], unique=False)
    op.create_index(op.f('ix_audit_logs_user_id'), 'audit_logs', ['user_id'], unique=False)
    
    # Create triggers
    op.execute("""
        CREATE TRIGGER update_api_keys_updated_at
        BEFORE UPDATE ON api_keys
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column();
    """)
    
    op.execute("""
        CREATE TRIGGER update_user_portfolios_updated_at
        BEFORE UPDATE ON user_portfolios
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column();
    """)
    
    op.execute("""
        CREATE TRIGGER update_user_preferences_updated_at
        BEFORE UPDATE ON user_preferences
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column();
    """)
    
    op.execute("""
        CREATE TRIGGER update_audit_logs_updated_at
        BEFORE UPDATE ON audit_logs
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column();
    """)


def downgrade() -> None:
    # Drop triggers
    op.execute('DROP TRIGGER IF EXISTS update_api_keys_updated_at ON api_keys')
    op.execute('DROP TRIGGER IF EXISTS update_user_portfolios_updated_at ON user_portfolios')
    op.execute('DROP TRIGGER IF EXISTS update_user_preferences_updated_at ON user_preferences')
    op.execute('DROP TRIGGER IF EXISTS update_audit_logs_updated_at ON audit_logs')
    
    # Drop indexes
    op.drop_index(op.f('ix_audit_logs_user_id'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_resource_type'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_event_type'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_event_category'), table_name='audit_logs')
    op.drop_index('idx_audit_user_time', table_name='audit_logs')
    op.drop_index('idx_audit_resource', table_name='audit_logs')
    op.drop_index('idx_audit_event_time', table_name='audit_logs')
    op.drop_index(op.f('ix_api_keys_key_hash'), table_name='api_keys')
    
    # Drop tables
    op.drop_table('audit_logs')
    op.drop_table('user_preferences')
    op.drop_table('user_portfolios')
    op.drop_table('api_keys')
    
    # Remove columns from users table
    op.drop_column('users', 'max_position_size')
    op.drop_column('users', 'max_daily_trades')
    op.drop_column('users', 'verified_at')
    op.drop_column('users', 'last_login_at')
    op.drop_column('users', 'is_verified')
    op.drop_column('users', 'phone_number')
    op.drop_column('users', 'full_name')