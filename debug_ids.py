import asyncio
from sqlalchemy import select
from app.models.user import User
from app.models.workshop import Workshop
from app.models.incidente import Incidente
from app.core.database import get_session_factory

async def debug_data():
    session_factory = get_session_factory()
    async with session_factory() as session:
        # 1. List all workshops and their users
        result = await session.execute(select(Workshop))
        workshops = result.scalars().all()
        print("--- WORKSHOPS IN DB ---")
        for w in workshops:
            print(f"ID: {w.id}, Workshop Name: {w.workshop_name}, Owner: {w.owner_name}, Email: {w.email}")
            
        # 2. List all incidents and their taller_id
        result = await session.execute(select(Incidente))
        incidents = result.scalars().all()
        print("\n--- INCIDENTS IN DB ---")
        taller_counts = {}
        for i in incidents:
            tid = i.taller_id
            if tid:
                taller_counts[tid] = taller_counts.get(tid, 0) + 1
        
        for tid, count in taller_counts.items():
            print(f"Taller ID: {tid} has {count} incidents")
            
        # 3. Check specific IDs
        # If Brotors is ID 1 in Admin View, but maybe their User ID is different?
        # No, Workshop.id is users.id.

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    loop.run_until_complete(debug_data())
