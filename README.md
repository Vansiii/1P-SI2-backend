# Backend - FastAPI

## Requisitos

- Python 3.10+
- Proyecto de Supabase con base de datos Postgres

## Instalacion

1. Crear entorno virtual:

   ```powershell
   python -m venv .venv
   ```

2. Activar entorno virtual en PowerShell:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

3. Instalar dependencias:

   ```powershell
   pip install -r requirements.txt
   ```

4. Configurar variables de entorno en `backend/.env`:

   ```env
   DATABASE_URL=postgresql://postgres.<PROJECT_REF>:<DB_PASSWORD>@db.<PROJECT_REF>.supabase.co:5432/postgres?sslmode=require
   ```

   Usa la cadena de conexion que te da Supabase en:

   - Supabase Dashboard > Project Settings > Database > Connection string

## Ejecutar en desarrollo

```powershell
uvicorn app.main:app --reload
```

La API estara disponible en:

- http://127.0.0.1:8000
- Documentacion Swagger: http://127.0.0.1:8000/docs
- Documentacion ReDoc: http://127.0.0.1:8000/redoc

## Verificar conexion a Supabase

- Salud general: http://127.0.0.1:8000/health
- Salud de base de datos: http://127.0.0.1:8000/db/health

Si la conexion a Supabase falla, la API mostrara un error de inicio con instrucciones para revisar `DATABASE_URL`.
