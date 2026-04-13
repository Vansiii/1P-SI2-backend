# 🚂 Guía de Despliegue en Railway - MecánicoYa Backend

## 📋 Requisitos Previos

- Cuenta en [Railway](https://railway.app)
- Repositorio Git (GitHub, GitLab o Bitbucket)
- Base de datos Supabase configurada

## 🚀 Pasos para Desplegar

### 1. Preparar el Repositorio

Asegúrate de que estos archivos estén en tu repositorio:

```
1P-SI2-backend/
├── app/
├── requirements.txt
├── Procfile
├── nixpacks.toml
├── .gitignore
└── README.md
```

**IMPORTANTE**: Verifica que `.env` esté en `.gitignore` para no subir credenciales.

### 2. Crear Proyecto en Railway

1. Ve a [railway.app](https://railway.app) e inicia sesión
2. Click en "New Project"
3. Selecciona "Deploy from GitHub repo"
4. Autoriza Railway a acceder a tu repositorio
5. Selecciona el repositorio `1P-SI2-Sistema-Ayuda-Taller`
6. Railway detectará automáticamente que es un proyecto Python

### 3. Configurar Variables de Entorno

En el panel de Railway, ve a la pestaña **Variables** y agrega:

#### 🔐 Variables Obligatorias

```bash
# Database
DATABASE_URL=postgresql://postgres.zwwixzyvakobmcktaitb:v3snG7L9fd2YIuCu@aws-1-sa-east-1.pooler.supabase.com:5432/postgres

# Supabase
SUPABASE_URL=https://zwwixzyvakobmcktaitb.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inp3d2l4enl2YWtvYm1ja3RhaXRiIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NTM2MjE2NiwiZXhwIjoyMDkwOTM4MTY2fQ.qTbU5twxCEo9v4nGo9gTEZ5IzsdsWWVp9tVz4r7g7PA

# Environment
ENVIRONMENT=production

# JWT - ⚠️ GENERAR NUEVA CLAVE
JWT_SECRET_KEY=GENERAR_NUEVA_CLAVE_CON_openssl_rand_hex_32
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440
REFRESH_TOKEN_EXPIRE_DAYS=7

# CORS - ⚠️ ACTUALIZAR CON TUS URLs REALES
CORS_ORIGINS=https://tu-frontend.vercel.app,https://tu-backend.railway.app

# Email
EMAIL_PROVIDER=api
EMAIL_FROM_ADDRESS=vallejosgabriel446@gmail.com
EMAIL_FROM_NAME=Sistema de Emergencias Vehiculares

# Brevo SMTP
BREVO_SMTP_HOST=smtp-relay.brevo.com
BREVO_SMTP_PORT=587
BREVO_SMTP_USER=tu_usuario_smtp@smtp-brevo.com
BREVO_SMTP_PASSWORD=tu_password_smtp_brevo
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
EMAIL_TIMEOUT=10

# Brevo API
BREVO_API_KEY=tu_api_key_brevo
BREVO_API_URL=https://api.brevo.com/v3/smtp/email

# Frontend URL - ⚠️ ACTUALIZAR
FRONTEND_URL=https://tu-frontend.vercel.app

# Security
PASSWORD_RESET_TOKEN_EXPIRE_MINUTES=60
OTP_EXPIRE_MINUTES=5
MAX_LOGIN_ATTEMPTS=5
LOCKOUT_DURATION_MINUTES=15

# Database Pool
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10
DB_POOL_TIMEOUT=30

# Rate Limiting
RATE_LIMIT_WHITELIST_IPS=
RATE_LIMIT_ADMIN_MULTIPLIER=3
```

### 4. Configurar el Directorio Raíz

Si tu backend está en un subdirectorio:

1. Ve a **Settings** → **Service**
2. En **Root Directory**, configura: `1P-SI2-backend`
3. Guarda los cambios

### 5. Generar Nueva Clave JWT (IMPORTANTE)

En tu terminal local, genera una nueva clave secreta:

```bash
# En Linux/Mac
openssl rand -hex 32

# En Windows PowerShell
python -c "import secrets; print(secrets.token_hex(32))"
```

Copia el resultado y actualiza `JWT_SECRET_KEY` en Railway.

### 6. Actualizar CORS Origins

Una vez desplegado, Railway te dará una URL como:
```
https://tu-proyecto.railway.app
```

Actualiza la variable `CORS_ORIGINS` con:
```
CORS_ORIGINS=https://tu-frontend-url.vercel.app,https://tu-proyecto.railway.app
```

### 7. Desplegar

Railway desplegará automáticamente cuando:
- Hagas push a tu rama principal (main/master)
- Cambies variables de entorno
- Hagas un redespliegue manual

### 8. Verificar el Despliegue

1. Ve a la pestaña **Deployments** en Railway
2. Espera a que el estado sea "Success" (verde)
3. Click en la URL generada para ver tu API
4. Verifica los endpoints:
   - `https://tu-proyecto.railway.app/` → Debe mostrar mensaje de bienvenida
   - `https://tu-proyecto.railway.app/health` → Debe retornar status OK
   - `https://tu-proyecto.railway.app/docs` → Documentación Swagger

## 🔧 Configuración Adicional

### Dominio Personalizado (Opcional)

1. Ve a **Settings** → **Networking**
2. Click en "Generate Domain" para obtener un dominio Railway
3. O configura tu propio dominio personalizado

### Logs y Monitoreo

- **Ver logs en tiempo real**: Pestaña "Logs" en Railway
- **Métricas**: Pestaña "Metrics" para CPU, memoria, red

### Ejecutar Migraciones

Si necesitas ejecutar migraciones de Alembic:

```bash
# Opción 1: Desde Railway CLI
railway run alembic upgrade head

# Opción 2: Agregar al comando de inicio en nixpacks.toml
cmd = "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT"
```

## 🐛 Troubleshooting

### Error: "Application failed to respond"

- Verifica que el comando de inicio use `--host 0.0.0.0`
- Asegúrate de que la app escuche en `$PORT`

### Error: "Database connection failed"

- Verifica que `DATABASE_URL` esté correctamente configurada
- Comprueba que Supabase permita conexiones desde Railway

### Error: "Module not found"

- Verifica que `requirements.txt` esté actualizado
- Asegúrate de que el directorio raíz esté bien configurado

### Logs no aparecen

- Verifica la configuración de logging en `app/core/logging.py`
- Railway captura stdout/stderr automáticamente

## 📊 Monitoreo de Salud

Railway monitoreará automáticamente tu aplicación. Puedes configurar health checks:

1. Ve a **Settings** → **Health Check**
2. Configura el endpoint: `/health`
3. Intervalo: 60 segundos

## 🔄 CI/CD Automático

Railway despliega automáticamente en cada push. Para control manual:

1. Ve a **Settings** → **Service**
2. Desactiva "Auto Deploy"
3. Despliega manualmente desde la pestaña "Deployments"

## 💰 Costos

Railway ofrece:
- **Plan Hobby**: $5/mes de crédito gratis
- **Plan Pro**: $20/mes con más recursos

Monitorea tu uso en la pestaña "Usage".

## 🔗 URLs Importantes

- Panel de Railway: https://railway.app/dashboard
- Documentación: https://docs.railway.app
- CLI de Railway: https://docs.railway.app/develop/cli

## 📝 Checklist Final

- [ ] Variables de entorno configuradas
- [ ] Nueva clave JWT generada
- [ ] CORS origins actualizados
- [ ] Directorio raíz configurado
- [ ] Despliegue exitoso (verde)
- [ ] Endpoints funcionando
- [ ] Logs sin errores
- [ ] Base de datos conectada
- [ ] Emails funcionando (Brevo)
- [ ] Frontend puede conectarse al backend

## 🎉 ¡Listo!

Tu backend FastAPI está desplegado en Railway y listo para producción.

**URL de tu API**: `https://tu-proyecto.railway.app`
**Documentación**: `https://tu-proyecto.railway.app/docs`
