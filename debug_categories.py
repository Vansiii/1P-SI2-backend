
import asyncio
from sqlalchemy import select, func
from app.core.database import get_session_factory
from app.models.incidente import Incidente
from app.models.categoria import Categoria

async def check():
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(
                Categoria.nombre,
                func.count(Incidente.id)
            )
            .join(Incidente, Incidente.categoria_id == Categoria.id)
            .group_by(Categoria.nombre)
        )
        data = result.all()
        print(f"--- INCIDENTS BY CATEGORY ({len(data)}) ---")
        for row in data:
            print(f"Category: {row[0]}, Count: {row[1]}")

if __name__ == "__main__":
    asyncio.run(check())
