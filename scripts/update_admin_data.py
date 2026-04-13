"""
Script para actualizar datos de administradores existentes.
Ejecutar con: python -m scripts.update_admin_data
"""
import asyncio
from sqlalchemy import select, update
from app.core.database import get_engine
from app.models.user import User
from app.models.administrator import Administrator


async def update_admin_data():
    """Actualiza los datos de administradores que no tienen first_name, last_name o phone."""
    engine = get_engine()
    
    async with engine.begin() as conn:
        # Buscar administradores sin datos completos
        result = await conn.execute(
            select(User).where(
                User.user_type == "admin",
                User.first_name == None
            )
        )
        admins = result.scalars().all()
        
        if not admins:
            print("✅ No hay administradores sin datos completos")
            return
        
        print(f"📝 Encontrados {len(admins)} administradores sin datos completos")
        
        for admin in admins:
            # Actualizar con datos por defecto
            await conn.execute(
                update(User)
                .where(User.id == admin.id)
                .values(
                    first_name="Admin",
                    last_name="Sistema",
                    phone="0000000000"
                )
            )
            print(f"✅ Actualizado administrador: {admin.email}")
        
        print(f"\n✅ Se actualizaron {len(admins)} administradores")


if __name__ == "__main__":
    print("🔧 Actualizando datos de administradores...")
    asyncio.run(update_admin_data())
    print("✅ Proceso completado")
