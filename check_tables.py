
import asyncio
from sqlalchemy import text
from app.core.database import get_session_factory

async def check():
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            await session.execute(text('SELECT 1 FROM workshop_financial_movements LIMIT 1'))
            print('Table workshop_financial_movements exists')
        except Exception as e:
            print(f'Table workshop_financial_movements error: {e}')
            
        try:
            await session.execute(text('SELECT 1 FROM transactions LIMIT 1'))
            print('Table transactions exists')
        except Exception as e:
            print(f'Table transactions error: {e}')

if __name__ == "__main__":
    asyncio.run(check())
