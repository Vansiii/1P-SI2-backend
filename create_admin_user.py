"""
Script para crear un usuario administrador.

Uso:
    python create_admin_user.py
"""
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db_session
from app.core.security import hash_password
from app.models.user import User
from app.core.permissions import UserRole
from datetime import datetime, UTC


async def create_admin_user():
    """Crear usuario administrador."""
    
    # Datos del administrador
    email = "jgabworkplace@gmail.com"
    password = "gabriel123A@"
    first_name = "Juan Gabriel"
    last_name = "Cordero"
    user_type = "admin"  # Valor correcto según constraint de BD
    
    print("=" * 60)
    print("CREACIÓN DE USUARIO ADMINISTRADOR")
    print("=" * 60)
    print(f"Email: {email}")
    print(f"Nombre: {first_name} {last_name}")
    print(f"Tipo: {user_type}")
    print("=" * 60)
    
    # Obtener sesión de base de datos
    async for session in get_db_session():
        try:
            # Verificar si el usuario ya existe
            from sqlalchemy import select
            result = await session.execute(
                select(User).where(User.email == email)
            )
            existing_user = result.scalar_one_or_none()
            
            if existing_user:
                print(f"\n⚠️  El usuario con email {email} ya existe.")
                print(f"   ID: {existing_user.id}")
                print(f"   Tipo: {existing_user.user_type}")
                print(f"   Activo: {existing_user.is_active}")
                
                # Preguntar si desea actualizar
                response = input("\n¿Desea actualizar este usuario a administrador? (s/n): ")
                if response.lower() == 's':
                    existing_user.user_type = user_type
                    existing_user.first_name = first_name
                    existing_user.last_name = last_name
                    existing_user.password_hash = hash_password(password)
                    existing_user.is_active = True
                    existing_user.updated_at = datetime.now(UTC)
                    
                    await session.commit()
                    await session.refresh(existing_user)
                    
                    print("\n✅ Usuario actualizado exitosamente!")
                    print(f"   ID: {existing_user.id}")
                    print(f"   Email: {existing_user.email}")
                    print(f"   Tipo: {existing_user.user_type}")
                else:
                    print("\n❌ Operación cancelada.")
                return
            
            # Crear nuevo usuario administrador
            hashed_password = hash_password(password)
            
            admin_user = User(
                email=email,
                password_hash=hashed_password,
                phone="",  # Campo requerido, puede estar vacío
                first_name=first_name,
                last_name=last_name,
                user_type=user_type,
                is_active=True,
                email_verified=True,  # Admin pre-verificado
                two_factor_enabled=False,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC)
            )
            
            session.add(admin_user)
            await session.commit()
            await session.refresh(admin_user)
            
            print("\n✅ Usuario administrador creado exitosamente!")
            print(f"   ID: {admin_user.id}")
            print(f"   Email: {admin_user.email}")
            print(f"   Nombre: {admin_user.first_name} {admin_user.last_name}")
            print(f"   Tipo: {admin_user.user_type}")
            print(f"   Activo: {admin_user.is_active}")
            print(f"   Email verificado: {admin_user.email_verified}")
            print("\n" + "=" * 60)
            print("CREDENCIALES DE ACCESO")
            print("=" * 60)
            print(f"Email: {email}")
            print(f"Contraseña: {password}")
            print("=" * 60)
            print("\nPuedes iniciar sesión en:")
            print("  - Frontend Web: http://localhost:4200")
            print("  - API Docs: http://localhost:8000/docs")
            print("\nEndpoint de login:")
            print("  POST http://localhost:8000/api/v1/auth/login")
            print("  Body: {")
            print(f'    "email": "{email}",')
            print(f'    "password": "{password}"')
            print("  }")
            print("=" * 60)
            
        except Exception as e:
            await session.rollback()
            print(f"\n❌ Error al crear usuario: {str(e)}")
            import traceback
            traceback.print_exc()
        finally:
            await session.close()
            break


if __name__ == "__main__":
    print("\n🚀 Iniciando creación de usuario administrador...\n")
    asyncio.run(create_admin_user())
    print("\n✨ Proceso completado.\n")
