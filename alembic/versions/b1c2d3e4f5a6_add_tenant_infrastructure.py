"""add_tenant_infrastructure_cu29_cu30_cu31

Revision ID: b1c2d3e4f5a6
Revises: h123456789ab
Create Date: 2026-05-26

This migration:
1. Creates tenants, subscription_plans, tenant_subscriptions, subscription_invoices tables
2. Adds tenant_id FK to 21 existing tenant-scoped tables
3. Adds nit to workshops
4. Backfills tenant data for existing workshops
5. Creates indexes for tenant_id columns
6. Seeds default subscription plans
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone

revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, None] = 'fix_cancellation_uniqueness'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ===== 1. Create new tables =====

    op.create_table(
        'tenants',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('workshop_id', sa.Integer(), sa.ForeignKey('workshops.id', ondelete='CASCADE'),
                  unique=True, nullable=False),
        sa.Column('owner_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('legal_name', sa.String(255), nullable=False),
        sa.Column('nit', sa.String(20), unique=True, nullable=False),
        sa.Column('slug', sa.String(100), unique=True, nullable=True),
        sa.Column('business_type', sa.String(50), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('reviewed_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(),
                  onupdate=sa.func.now(), nullable=False),
    )
    op.create_index('idx_tenants_status', 'tenants', ['status'])
    op.create_index('idx_tenants_nit', 'tenants', ['nit'])

    op.create_table(
        'subscription_plans',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('code', sa.String(50), unique=True, nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('price', sa.Numeric(10, 2), nullable=False, server_default='0'),
        sa.Column('billing_period', sa.String(20), nullable=False, server_default='monthly'),
        sa.Column('stripe_price_id', sa.String(255), nullable=True),
        sa.Column('stripe_product_id', sa.String(255), nullable=True),
        sa.Column('max_technicians', sa.Integer(), server_default='5'),
        sa.Column('max_services', sa.Integer(), server_default='20'),
        sa.Column('enable_kpis', sa.Boolean(), server_default=sa.text('false')),
        sa.Column('enable_reports', sa.Boolean(), server_default=sa.text('false')),
        sa.Column('enable_realtime_tracking', sa.Boolean(), server_default=sa.text('false')),
        sa.Column('enable_quotes', sa.Boolean(), server_default=sa.text('false')),
        sa.Column('enable_voice_reports', sa.Boolean(), server_default=sa.text('false')),
        sa.Column('enable_priority_support', sa.Boolean(), server_default=sa.text('false')),
        sa.Column('enable_api_access', sa.Boolean(), server_default=sa.text('false')),
        sa.Column('enable_white_label', sa.Boolean(), server_default=sa.text('false')),
        sa.Column('sort_order', sa.Integer(), server_default='0'),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(),
                  onupdate=sa.func.now(), nullable=False),
    )

    op.create_table(
        'tenant_subscriptions',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('plan_id', sa.Integer(), sa.ForeignKey('subscription_plans.id'), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='active'),
        sa.Column('current_period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('current_period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('cancel_at_period_end', sa.Boolean(), server_default=sa.text('false')),
        sa.Column('trial_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('payment_provider', sa.String(20), server_default='stripe'),
        sa.Column('provider_subscription_id', sa.String(255), nullable=True),
        sa.Column('provider_customer_id', sa.String(255), nullable=True),
        sa.Column('grace_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('suspended_reason', sa.Text(), nullable=True),
        sa.Column('suspended_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(),
                  onupdate=sa.func.now(), nullable=False),
    )
    op.create_index('idx_ts_tenant', 'tenant_subscriptions', ['tenant_id'])
    op.create_index('idx_ts_status', 'tenant_subscriptions', ['status'])

    op.create_table(
        'subscription_invoices',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('subscription_id', sa.Integer(), sa.ForeignKey('tenant_subscriptions.id'), nullable=True),
        sa.Column('amount', sa.Numeric(10, 2), nullable=False),
        sa.Column('currency', sa.String(3), server_default='usd'),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('stripe_invoice_id', sa.String(255), unique=True, nullable=True),
        sa.Column('stripe_payment_intent_id', sa.String(255), nullable=True),
        sa.Column('invoice_url', sa.String(500), nullable=True),
        sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('idx_si_tenant', 'subscription_invoices', ['tenant_id'])

    # ===== 2. Add tenant_id + nit to workshops =====
    op.add_column('workshops', sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id'), nullable=True))
    op.add_column('workshops', sa.Column('nit', sa.String(20), nullable=True))
    op.create_index('ix_workshops_tenant_id', 'workshops', ['tenant_id'])
    op.create_index('ix_workshops_nit', 'workshops', ['nit'], unique=True)

    # ===== 3. Add tenant_id to all tenant-scoped tables =====
    tenant_scoped_tables = [
        'incidentes', 'technicians', 'transactions',
        'platform_commissions', 'workshop_balances', 'withdrawals',
        'workshop_financial_movements', 'workshop_settlements',
        'technician_especialidades', 'technician_location_history',
        'workshop_schedules', 'servicios_taller',
        'conversations', 'messages', 'notifications',
        'audit_logs', 'outbox_events', 'event_log',
        'service_ratings', 'assignment_attempts', 'cancellation_requests',
    ]

    for table in tenant_scoped_tables:
        op.add_column(table, sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id'), nullable=True))
        op.create_index(f'ix_{table}_tenant_id', table, ['tenant_id'])

    # ===== 4. Seed default subscription plans =====
    plans_table = sa.table(
        'subscription_plans',
        sa.column('code', sa.String),
        sa.column('name', sa.String),
        sa.column('description', sa.String),
        sa.column('price', sa.Numeric),
        sa.column('billing_period', sa.String),
        sa.column('max_technicians', sa.Integer),
        sa.column('max_services', sa.Integer),
        sa.column('enable_kpis', sa.Boolean),
        sa.column('enable_reports', sa.Boolean),
        sa.column('enable_realtime_tracking', sa.Boolean),
        sa.column('enable_quotes', sa.Boolean),
        sa.column('enable_priority_support', sa.Boolean),
        sa.column('sort_order', sa.Integer),
    )

    op.bulk_insert(plans_table, [
        {
            'code': 'basic', 'name': 'Plan Basico', 'price': 0.00, 'billing_period': 'monthly',
            'max_technicians': 3, 'max_services': 10,
            'enable_kpis': False, 'enable_reports': False,
            'enable_realtime_tracking': False, 'enable_quotes': False,
            'enable_priority_support': False, 'sort_order': 1,
            'description': 'Funcionalidades esenciales para talleres pequenos',
        },
        {
            'code': 'pro', 'name': 'Plan Profesional', 'price': 29.99, 'billing_period': 'monthly',
            'max_technicians': 10, 'max_services': 30,
            'enable_kpis': True, 'enable_reports': True,
            'enable_realtime_tracking': True, 'enable_quotes': True,
            'enable_priority_support': False, 'sort_order': 2,
            'description': 'Para talleres en crecimiento con analitica avanzada',
        },
        {
            'code': 'business', 'name': 'Plan Business', 'price': 59.99, 'billing_period': 'monthly',
            'max_technicians': 25, 'max_services': 80,
            'enable_kpis': True, 'enable_reports': True,
            'enable_realtime_tracking': True, 'enable_quotes': True,
            'enable_priority_support': True, 'sort_order': 3,
            'description': 'Gestion completa con reportes y tracking en tiempo real',
        },
        {
            'code': 'enterprise', 'name': 'Plan Empresarial', 'price': 99.99, 'billing_period': 'monthly',
            'max_technicians': 100, 'max_services': 500,
            'enable_kpis': True, 'enable_reports': True,
            'enable_realtime_tracking': True, 'enable_quotes': True,
            'enable_priority_support': True, 'sort_order': 4,
            'description': 'Maximas funcionalidades, API access y white label',
        },
    ])

    # ===== 5. Backfill: create tenant for each existing workshop =====
    conn = op.get_bind()

    # Check if there are existing workshops without tenants
    result = conn.execute(sa.text("SELECT COUNT(*) FROM workshops WHERE tenant_id IS NULL"))
    count = result.scalar()
    if count and count > 0:
        # Insert tenants for existing workshops
        conn.execute(sa.text("""
            INSERT INTO tenants (workshop_id, owner_user_id, legal_name, nit, slug, status, created_at, updated_at)
            SELECT
                w.id,
                w.id,
                w.workshop_name,
                COALESCE(w.nit, 'LEGACY-' || w.id::TEXT),
                LOWER(REGEXP_REPLACE(w.workshop_name, '[^a-zA-Z0-9]', '-', 'g')) || '-' || w.id::TEXT,
                'active',
                COALESCE(u.created_at, NOW()),
                NOW()
            FROM workshops w
            JOIN users u ON u.id = w.id
            WHERE w.tenant_id IS NULL
        """))

        # Update workshops with tenant_id
        conn.execute(sa.text("""
            UPDATE workshops w
            SET tenant_id = t.id
            FROM tenants t
            WHERE t.workshop_id = w.id AND w.tenant_id IS NULL
        """))

        # Backfill tenant_id in all related tables
        backfill_queries = [
            ("incidentes", "taller_id"),
            ("technicians", "workshop_id"),
            ("transactions", "workshop_id"),
            ("platform_commissions", "workshop_id"),
            ("workshop_balances", "workshop_id"),
            ("withdrawals", "workshop_id"),
            ("workshop_financial_movements", "workshop_id"),
            ("workshop_settlements", "workshop_id"),
            ("workshop_schedules", "workshop_id"),
            ("servicios_taller", "taller_id"),
            ("conversations", "workshop_id"),
            ("audit_logs", "user_id"),
            ("service_ratings", "workshop_id"),
        ]

        for table, fk_column in backfill_queries:
            if fk_column == "user_id":
                # For audit_logs, resolve via users -> workshops
                conn.execute(sa.text(f"""
                    UPDATE {table} a
                    SET tenant_id = w.tenant_id
                    FROM users u
                    JOIN workshops w ON w.id = u.id AND u.user_type = 'workshop'
                    WHERE a.{fk_column} = u.id AND a.tenant_id IS NULL
                """))
            else:
                conn.execute(sa.text(f"""
                    UPDATE {table} t
                    SET tenant_id = w.tenant_id
                    FROM workshops w
                    WHERE t.{fk_column} = w.id AND t.tenant_id IS NULL
                """))

        # For tables that relate via other tables, use cascade approach
        # Messages via incidents
        conn.execute(sa.text("""
            UPDATE messages m
            SET tenant_id = i.tenant_id
            FROM incidentes i
            WHERE m.incident_id = i.id AND m.tenant_id IS NULL
        """))

        # Notifications via users (approximate, for workshop users)
        conn.execute(sa.text("""
            UPDATE notifications n
            SET tenant_id = w.tenant_id
            FROM users u
            JOIN workshops w ON w.id = u.id AND u.user_type = 'workshop'
            WHERE n.user_id = u.id AND n.tenant_id IS NULL
        """))

        # Outbox events / event_log: set NULL (admin/system events may be cross-tenant)
        # technician_especialidades via technician
        conn.execute(sa.text("""
            UPDATE technician_especialidades te
            SET tenant_id = t.tenant_id
            FROM technicians t
            WHERE te.technician_id = t.id AND te.tenant_id IS NULL
        """))

        # technician_location_history via technician
        conn.execute(sa.text("""
            UPDATE technician_location_history tlh
            SET tenant_id = t.tenant_id
            FROM technicians t
            WHERE tlh.technician_id = t.id AND tlh.tenant_id IS NULL
        """))

        # assignment_attempts via incident
        conn.execute(sa.text("""
            UPDATE assignment_attempts aa
            SET tenant_id = i.tenant_id
            FROM incidentes i
            WHERE aa.incident_id = i.id AND aa.tenant_id IS NULL
        """))

        # cancellation_requests via incident
        conn.execute(sa.text("""
            UPDATE cancellation_requests cr
            SET tenant_id = i.tenant_id
            FROM incidentes i
            WHERE cr.incident_id = i.id AND cr.tenant_id IS NULL
        """))

        # Assign basic plan to legacy tenants
        conn.execute(sa.text("""
            INSERT INTO tenant_subscriptions (tenant_id, plan_id, status, current_period_start, current_period_end)
            SELECT t.id, sp.id, 'active', NOW(), NOW() + INTERVAL '100 years'
            FROM tenants t
            CROSS JOIN (SELECT id FROM subscription_plans WHERE code = 'basic') sp
            WHERE t.status = 'active'
              AND NOT EXISTS (SELECT 1 FROM tenant_subscriptions ts WHERE ts.tenant_id = t.id)
        """))


def downgrade() -> None:
    # Remove tenant_id from all tables (reverse order)
    tenant_scoped_tables = [
        'cancellation_requests', 'assignment_attempts', 'service_ratings',
        'event_log', 'outbox_events', 'audit_logs',
        'notifications', 'messages', 'conversations',
        'servicios_taller', 'workshop_schedules',
        'technician_location_history', 'technician_especialidades',
        'workshop_settlements', 'workshop_financial_movements',
        'withdrawals', 'workshop_balances', 'platform_commissions',
        'transactions', 'technicians', 'incidentes',
    ]

    for table in tenant_scoped_tables:
        op.drop_index(f'ix_{table}_tenant_id', table_name=table)
        op.drop_column(table, 'tenant_id')

    # Remove from workshops
    op.drop_index('ix_workshops_nit', table_name='workshops')
    op.drop_index('ix_workshops_tenant_id', table_name='workshops')
    op.drop_column('workshops', 'nit')
    op.drop_column('workshops', 'tenant_id')

    # Drop new tables
    op.drop_index('idx_si_tenant', table_name='subscription_invoices')
    op.drop_table('subscription_invoices')
    op.drop_index('idx_ts_status', table_name='tenant_subscriptions')
    op.drop_index('idx_ts_tenant', table_name='tenant_subscriptions')
    op.drop_table('tenant_subscriptions')
    op.drop_table('subscription_plans')
    op.drop_index('idx_tenants_nit', table_name='tenants')
    op.drop_index('idx_tenants_status', table_name='tenants')
    op.drop_table('tenants')
