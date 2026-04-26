"""fix event_priority enum values to lowercase

Revision ID: i4j5k6l7m8n9
Revises: g3c4d5e6f7h8
Create Date: 2026-04-23 05:20:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'i4j5k6l7m8n9'
down_revision = 'h123456789ab'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Fix event_priority enum to use lowercase values.
    
    The enum was created with uppercase values (LOW, MEDIUM, HIGH, CRITICAL)
    but the code expects lowercase values (low, medium, high, critical).
    """
    conn = op.get_bind()
    
    # Check if enum exists and has uppercase values
    result = conn.execute(sa.text("""
        SELECT enumlabel 
        FROM pg_enum 
        WHERE enumtypid = (
            SELECT oid 
            FROM pg_type 
            WHERE typname = 'event_priority'
        )
        ORDER BY enumsortorder
    """))
    
    current_values = [row[0] for row in result]
    
    # If enum has uppercase values, we need to fix it
    if current_values and current_values[0].isupper():
        # Create a temporary enum with lowercase values
        conn.execute(sa.text(
            "CREATE TYPE event_priority_new AS ENUM ('low', 'medium', 'high', 'critical')"
        ))
        
        # Update outbox_events table to use new enum
        # First, convert to text
        conn.execute(sa.text(
            "ALTER TABLE outbox_events ALTER COLUMN priority TYPE text"
        ))
        
        # Convert uppercase to lowercase
        conn.execute(sa.text(
            "UPDATE outbox_events SET priority = LOWER(priority)"
        ))
        
        # Convert to new enum
        conn.execute(sa.text(
            "ALTER TABLE outbox_events ALTER COLUMN priority TYPE event_priority_new USING priority::event_priority_new"
        ))
        
        # Drop old enum
        conn.execute(sa.text(
            "DROP TYPE event_priority"
        ))
        
        # Rename new enum to original name
        conn.execute(sa.text(
            "ALTER TYPE event_priority_new RENAME TO event_priority"
        ))
        
        # Re-add default
        conn.execute(sa.text(
            "ALTER TABLE outbox_events ALTER COLUMN priority SET DEFAULT 'medium'::event_priority"
        ))
        
        print("✅ Fixed event_priority enum values to lowercase")
    else:
        print("✅ event_priority enum already has correct lowercase values")


def downgrade() -> None:
    """
    Revert event_priority enum to uppercase values.
    """
    conn = op.get_bind()
    
    # Create a temporary enum with uppercase values
    conn.execute(sa.text(
        "CREATE TYPE event_priority_new AS ENUM ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')"
    ))
    
    # Update outbox_events table to use new enum
    # First, convert to text
    conn.execute(sa.text(
        "ALTER TABLE outbox_events ALTER COLUMN priority DROP DEFAULT"
    ))
    
    conn.execute(sa.text(
        "ALTER TABLE outbox_events ALTER COLUMN priority TYPE text"
    ))
    
    # Convert lowercase to uppercase
    conn.execute(sa.text(
        "UPDATE outbox_events SET priority = UPPER(priority)"
    ))
    
    # Convert to new enum
    conn.execute(sa.text(
        "ALTER TABLE outbox_events ALTER COLUMN priority TYPE event_priority_new USING priority::event_priority_new"
    ))
    
    # Drop old enum
    conn.execute(sa.text(
        "DROP TYPE event_priority"
    ))
    
    # Rename new enum to original name
    conn.execute(sa.text(
        "ALTER TYPE event_priority_new RENAME TO event_priority"
    ))
    
    # Re-add default
    conn.execute(sa.text(
        "ALTER TABLE outbox_events ALTER COLUMN priority SET DEFAULT 'MEDIUM'::event_priority"
    ))
