# Backend - FastAPI

MecanicoYa - Plataforma de asistencia mecánica con autenticación avanzada y seguridad robusta.

## Requisitos

- Python 3.10+
- Proyecto de Supabase con base de datos Postgres

## Instalación

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

4. Configurar variables de entorno:

   Copia el archivo `.env.example` a `.env` y configura las variables:

   ```powershell
   Copy-Item .env.example .env
   ```

   Edita `.env` con tus credenciales reales.

## Variables de Entorno

### Base de Datos

```env
DATABASE_URL=postgresql://postgres.<PROJECT_REF>:<DB_PASSWORD>@db.<PROJECT_REF>.supabase.co:5432/postgres?sslmode=require
```

Obtén la cadena de conexión en: Supabase Dashboard > Project Settings > Database > Connection string

### JWT y Seguridad

```env
# IMPORTANTE: Cambia esta clave en producción
JWT_SECRET_KEY=tu-clave-secreta-minimo-32-caracteres-muy-segura
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
```

**Requisitos de JWT_SECRET_KEY:**
- Mínimo 32 caracteres
- No usar el valor por defecto
- Usar caracteres aleatorios y seguros

### CORS

```env
CORS_ORIGINS=http://localhost:4200,http://127.0.0.1:4200
```

Lista de orígenes permitidos separados por comas. No dejar vacío.

### Email (Brevo)

```env
# Proveedor: smtp o api
EMAIL_PROVIDER=smtp
EMAIL_FROM_ADDRESS=noreply@tu-dominio.com
EMAIL_FROM_NAME=Sistema de Emergencias Vehiculares

# Configuración SMTP (si EMAIL_PROVIDER=smtp)
BREVO_SMTP_HOST=smtp-relay.brevo.com
BREVO_SMTP_PORT=587
BREVO_SMTP_USER=tu-usuario-brevo
BREVO_SMTP_PASSWORD=tu-password-brevo

# Configuración API (si EMAIL_PROVIDER=api)
BREVO_API_KEY=tu-api-key-brevo
```

**Obtener credenciales de Brevo:**
1. Crear cuenta en [Brevo](https://www.brevo.com/)
2. SMTP: Settings > SMTP & API > SMTP
3. API: Settings > SMTP & API > API Keys

### Configuración de Seguridad

```env
PASSWORD_RESET_TOKEN_EXPIRE_MINUTES=60
OTP_EXPIRE_MINUTES=5
MAX_LOGIN_ATTEMPTS=5
LOCKOUT_DURATION_MINUTES=5
```

## Ejecutar en Desarrollo

### Para desarrollo web (solo localhost)
```powershell
uvicorn app.main:app --reload
```

### Para desarrollo con app móvil (accesible desde la red local)
```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

El parámetro `--host 0.0.0.0` permite que el servidor sea accesible desde otros dispositivos en tu red local (necesario para probar con dispositivos móviles físicos).

La API estará disponible en:

- Localhost: http://127.0.0.1:8000
- Red local: http://TU_IP_LOCAL:8000 (ejemplo: http://192.168.1.4:8000)
- Documentación Swagger: http://127.0.0.1:8000/docs
- Documentación ReDoc: http://127.0.0.1:8000/redoc

**Nota:** Para encontrar tu IP local:
- Windows: `ipconfig` (busca "Dirección IPv4")
- Linux/Mac: `ifconfig` o `ip addr`

## Verificar Conexión

- Salud general: http://127.0.0.1:8000/health
- Salud de base de datos: http://127.0.0.1:8000/db/health

## Arquitectura de Usuarios

El sistema usa **herencia de tabla (Table Per Type)** para diferentes tipos de usuarios:

- **User** (tabla base): Campos comunes (email, password, user_type)
- **Client**: Clientes finales (app móvil)
- **Workshop**: Talleres mecánicos (app web)
- **Technician**: Técnicos de taller (web + móvil)
- **Administrator**: Administradores del sistema (web + móvil)

## Endpoints de Autenticación

### Registro
- `POST /api/v1/clients/register`: Registrar cliente
- `POST /api/v1/auth/register`: Registrar taller
- `POST /api/v1/technicians/register`: Registrar técnico (requiere auth de taller/admin)
- `POST /api/v1/administrators/register`: Registrar administrador (requiere auth de admin)

### Login y Sesión
- `POST /api/v1/auth/login/unified`: Iniciar sesión para cualquier tipo de usuario
- `POST /api/v1/auth/login/2fa`: Completar login con OTP 2FA
- `POST /api/v1/auth/login`: Login específico de taller (compatibilidad)
- `POST /api/v1/auth/logout`: Cerrar sesión
- `POST /api/v1/tokens/refresh`: Renovar access token
- `POST /api/v1/tokens/revoke-all`: Cerrar todas las sesiones del usuario actual
- `GET /api/v1/auth/me`: Obtener perfil actual
- `PATCH /api/v1/auth/me`: Actualizar perfil actual
- `DELETE /api/v1/auth/me`: Desactivar cuenta actual

### Recuperación de Contraseña
- `POST /api/v1/password/reset/request`: Solicitar recuperación
- `POST /api/v1/password/reset`: Resetear contraseña
- `POST /api/v1/password/change`: Cambiar contraseña (protegido)

### Autenticación de Dos Factores (2FA)
- `POST /api/v1/auth/2fa/enable`: Activar 2FA (protegido)
- `POST /api/v1/auth/2fa/verify`: Verificar código OTP
- `POST /api/v1/auth/2fa/disable`: Desactivar 2FA (protegido)
- `POST /api/v1/auth/2fa/resend`: Reenviar código OTP

## Características de Seguridad

✅ **Implementado:**
- Hashing de contraseñas con PBKDF2-SHA256 (390,000 iteraciones)
- JWT con access y refresh tokens
- Revocación de tokens
- Validación de fuerza de contraseñas
- Bloqueo por intentos fallidos
- Autenticación de dos factores (2FA) por email
- Rate limiting
- Auditoría de acciones críticas

## Modelos de Base de Datos

### Autenticación
- `users`: Tabla base de usuarios
- `clients`: Clientes finales
- `workshops`: Talleres mecánicos
- `technicians`: Técnicos de taller
- `administrators`: Administradores
- `refresh_tokens`: Tokens de renovación
- `revoked_tokens`: Tokens revocados
- `password_reset_tokens`: Tokens de recuperación
- `two_factor_auth`: Configuración 2FA
- `login_attempts`: Intentos de login
- `audit_logs`: Auditoría de acciones

## Desarrollo

### Instalar Dependencias de Desarrollo

```powershell
pip install -r requirements.txt
```

### Ejecutar Tests

```powershell
pytest
```

### Linting

```powershell
ruff check .
```

## Producción

### Despliegue en Railway

Para desplegar en Railway, consulta la [Guía de Despliegue en Railway](docs/RAILWAY_DEPLOYMENT.md).

**Resumen rápido:**

1. **Credenciales de Firebase:** Usa el script helper para convertir el JSON:
   ```bash
   python scripts/prepare_firebase_for_railway.py firebase-service-account.json
   ```
   Luego copia la salida y pégala en Railway como variable `FIREBASE_CREDENTIALS_JSON`

2. **Variables de entorno críticas en Railway:**
   - `DATABASE_URL`: URL de Supabase con `?sslmode=require`
   - `JWT_SECRET_KEY`: Clave segura única (32+ caracteres)
   - `CORS_ORIGINS`: URLs de tu frontend
   - `FIREBASE_CREDENTIALS_JSON`: JSON de Firebase en una línea
   - `ENVIRONMENT=production`
   - `DEBUG=false`

3. **Build Command:** `pip install -r requirements.txt`
4. **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

### Checklist de Seguridad

- [ ] Cambiar `JWT_SECRET_KEY` a valor fuerte y único
- [ ] Configurar `CORS_ORIGINS` con dominios específicos
- [ ] Configurar credenciales de Brevo
- [ ] Habilitar HTTPS
- [ ] Configurar rate limiting
- [ ] Revisar logs de seguridad
- [ ] Configurar monitoreo de errores

### Variables Críticas

Asegúrate de configurar estas variables en producción:

```env
# Seguridad
JWT_SECRET_KEY=<clave-super-segura-minimo-32-caracteres>
ENVIRONMENT=production
DEBUG=false

# Base de datos
DATABASE_URL=<url-de-produccion-con-sslmode-require>

# CORS
CORS_ORIGINS=https://tu-dominio.com

# Email
EMAIL_FROM_ADDRESS=<email-verificado>
BREVO_SMTP_USER=<credenciales-reales>
BREVO_SMTP_PASSWORD=<credenciales-reales>

# Firebase (Railway)
FIREBASE_CREDENTIALS_JSON=<json-minificado-en-una-linea>
FIREBASE_PROJECT_ID=<tu-project-id>
```

## 📚 Documentación Adicional

- [Guía de Despliegue en Railway](docs/RAILWAY_DEPLOYMENT.md)
- [Scripts de Utilidad](scripts/README.md)

## Soporte

Para más información, consulta:
- [Documentación de FastAPI](https://fastapi.tiangolo.com/)
- [Documentación de Supabase](https://supabase.com/docs)
- [Documentación de Brevo](https://developers.brevo.com/)
