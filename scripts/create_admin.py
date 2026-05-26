"""
Script to create an administrator user.
"""
import asyncio
from sqlalchemy import select
from app.core.database import get_session_factory
from app.models.administrator import Administrator
from app.core.security import get_password_hash


async def create_admin():
    """Create an administrator user."""
    session_factory = get_session_factory()
    
    print("\n" + "="*60)
    print("CREATE ADMINISTRATOR")
    print("="*60 + "\n")
    
    # Get admin details
    email = input("Email: ").strip()
    password = input("Password: ").strip()
    first_name = input("First Name: ").strip()
    last_name = input("Last Name: ").strip()
    phone = input("Phone (optional): ").strip() or None
    
    if not email or not password or not first_name or not last_name:
        print("\n❌ Email, password, first name, and last name are required!")
        return
    
    async with session_factory() as session:
        # Check if email already exists
        result = await session.execute(
            select(Administrator).where(Administrator.email == email)
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            print(f"\n❌ Administrator with email {email} already exists!")
            return
        
        # Create administrator
        admin = Administrator(
            email=email,
            password_hash=get_password_hash(password),
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            is_active=True
        )
        
        session.add(admin)
        await session.commit()
        await session.refresh(admin)
        
        print(f"\n✅ Administrator created successfully!")
        print(f"   ID: {admin.id}")
        print(f"   Email: {admin.email}")
        print(f"   Name: {admin.first_name} {admin.last_name}")
        print(f"   Active: {admin.is_active}")
        print("\n" + "="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(create_admin())
