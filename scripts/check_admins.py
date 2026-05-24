"""
Script to check if there are active administrators in the database.
"""
import asyncio
from sqlalchemy import select
from app.core.database import get_session_factory
from app.models.user import User


async def check_admins():
    """Check for active administrators."""
    session_factory = get_session_factory()
    
    async with session_factory() as session:
        # Get all administrators (user_type = 'admin')
        result = await session.execute(
            select(User).where(User.user_type == "admin")
        )
        admins = result.scalars().all()
        
        print(f"\n{'='*60}")
        print(f"ADMINISTRATORS IN DATABASE")
        print(f"{'='*60}\n")
        
        if not admins:
            print("❌ No administrators found in database!")
            print("\nNote: Looking for users with user_type = 'admin'")
        else:
            print(f"Found {len(admins)} administrator(s):\n")
            for admin in admins:
                status = "✅ ACTIVE" if admin.is_active else "❌ INACTIVE"
                print(f"  {status} - ID: {admin.id}, Email: {admin.email}, Name: {admin.first_name} {admin.last_name}")
        
        print(f"\n{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(check_admins())
