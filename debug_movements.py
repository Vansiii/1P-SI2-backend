
import asyncio
from sqlalchemy import select
from app.core.database import get_session_factory
from app.models.financial_movement import WorkshopFinancialMovement

async def debug_movements():
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(WorkshopFinancialMovement))
        movements = result.scalars().all()
        print(f"--- MOVEMENTS ({len(movements)}) ---")
        for m in movements:
            print(f"ID: {m.id}, Workshop ID: {m.workshop_id}, Amount: {m.amount}, Type: {m.movement_type}, Date: {m.created_at}")

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    loop.run_until_complete(debug_movements())
