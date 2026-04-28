
import asyncio
from sqlalchemy import select
from app.core.database import get_session_factory
from app.models.transaction import Transaction

async def debug_transactions():
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(Transaction))
        transactions = result.scalars().all()
        print(f"--- TRANSACTIONS ({len(transactions)}) ---")
        for t in transactions:
            print(f"ID: {t.id}, Workshop ID: {t.workshop_id}, Amount: {t.amount}, Commission: {t.commission}, WorkshopAmount: {t.workshop_amount}, Status: {t.status}, Date: {t.created_at}")

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    loop.run_until_complete(debug_transactions())
