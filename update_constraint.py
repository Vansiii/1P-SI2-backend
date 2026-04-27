import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("No DATABASE_URL found")
    exit(1)

# Ensure it's using the asyncpg driver
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

async def update_constraint():
    engine = create_async_engine(DATABASE_URL)
    
    async with engine.begin() as conn:
        print("Reverting incidents from aceptado to asignado...")
        try:
            await conn.execute(
                __import__('sqlalchemy').text("UPDATE incidentes SET estado_actual = 'asignado' WHERE estado_actual NOT IN ('pendiente', 'asignado', 'en_proceso', 'resuelto', 'cancelado', 'sin_taller_disponible')")
            )
        except Exception as e:
            print(f"Could not revert incidents: {e}")
            
        print("Dropping old constraint...")
        try:
            await conn.execute(
                __import__('sqlalchemy').text("ALTER TABLE incidentes DROP CONSTRAINT IF EXISTS check_estado_actual_valid")
            )
        except Exception as e:
            print(f"Could not drop constraint: {e}")
            
        print("Adding new constraint...")
        try:
            await conn.execute(
                __import__('sqlalchemy').text(
                    "ALTER TABLE incidentes ADD CONSTRAINT check_estado_actual_valid "
                    "CHECK (estado_actual IN ('pendiente', 'asignado', 'en_proceso', 'resuelto', 'cancelado', 'sin_taller_disponible'))"
                )
            )
        except Exception as e:
            print(f"Could not add constraint: {e}")
            
    print("Done!")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(update_constraint())
