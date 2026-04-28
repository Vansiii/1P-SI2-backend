import asyncio
from sqlalchemy import select, func
from app.core.database import get_session_factory
from app.models.incidente import Incidente
from app.models.transaction import Transaction

async def inspect_db():
    factory = get_session_factory()
    async with factory() as session:
        # Count incidents
        inc_count = await session.scalar(select(func.count(Incidente.id)))
        inc_states = await session.execute(select(Incidente.estado_actual, func.count(Incidente.id)).group_by(Incidente.estado_actual))
        
        # Count transactions
        trans_count = await session.scalar(select(func.count(Transaction.id)))
        trans_states = await session.execute(select(Transaction.status, func.count(Transaction.id)).group_by(Transaction.status))

        # Resolved incidents dates
        res_dates = await session.execute(select(Incidente.created_at).where(Incidente.estado_actual == "resuelto"))
        
        # Completed transactions dates
        trans_dates = await session.execute(select(Transaction.created_at).where(Transaction.status == "completed"))

        print(f"Total Incidents: {inc_count}")
        for state, count in inc_states:
            print(f"  - {state}: {count}")
        
        print("\nResolved Incident Dates:")
        for date, in res_dates:
            print(f"  - {date}")

        print(f"\nTotal Transactions: {trans_count}")
        for status, count in trans_states:
            print(f"  - {status}: {count}")
        
        print("\nCompleted Transaction Dates:")
        for date, in trans_dates:
            print(f"  - {date}")

if __name__ == "__main__":
    asyncio.run(inspect_db())
