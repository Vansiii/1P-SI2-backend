
import asyncio
from sqlalchemy import select
from app.core.database import SessionLocal
from app.models.user import User
from app.models.workshop import Workshop
from app.models.incidente import Incidente

async def check_ids():
    async with SessionLocal() as session:
        # Get all workshops
        result = await session.execute(select(Workshop))
        workshops = result.scalars().all()
        print(f"--- WORKSHOPS ({len(workshops)}) ---")
        for w in workshops:
            print(f"Workshop ID: {w.id}, Name: {w.workshop_name}, Email: {w.email}")
            
        # Get all incidents and their taller_id
        result = await session.execute(select(Incidente))
        incidents = result.scalars().all()
        print(f"\n--- INCIDENTS ({len(incidents)}) ---")
        for i in incidents:
            if i.taller_id:
                print(f"Incident ID: {i.id}, Taller ID: {i.taller_id}")
            
if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    loop.run_until_complete(check_ids())
