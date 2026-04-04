# Backend - FastAPI

## Requisitos

- Python 3.10+

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

## Ejecutar en desarrollo

```powershell
uvicorn app.main:app --reload
```

La API estara disponible en:

- http://127.0.0.1:8000
- Documentacion Swagger: http://127.0.0.1:8000/docs
- Documentacion ReDoc: http://127.0.0.1:8000/redoc
