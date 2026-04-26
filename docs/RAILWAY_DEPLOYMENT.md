# Guía de Despliegue en Railway

Esta guía te ayudará a desplegar el backend de MecánicoYa en Railway.

## 📋 Pre-requisitos

- Cuenta en [Railway](https://railway.app/)
- Proyecto de Supabase configurado
- Credenciales de Firebase (archivo JSON)
- Credenciales de Brevo (opcional, para emails)

## 🚀 Pasos de Despliegue

### 1. Crear Proyecto en Railway

1. Ve a [Railway](https://railway.app/) e inicia sesión
2. Click en "New Project"
3. Selecciona "Deploy from GitHub repo"
4. Conecta tu repositorio de GitHub
5. Selecciona el repositorio `1P-SI2-backend`

### 2. Configurar Variables de Entorno

Ve a la pestaña "Variables" en tu proyecto de Railway y agrega las siguientes variables:

#### 🔐 Base de Datos (Supabase)

```env
DATABASE_URL=postgresql://postgres.<PROJECT_REF>:<DB_PASSWORD>@db.<PROJECT_REF>.supabase.co:5432/postgres?sslmode=require
```

**Obtener de:** Supabase Dashboard > Project Settings > Database > Connection string

#### 🔑 JWT y Seguridad

```env
JWT_SECRET_KEY=tu-clave-super-secreta-minimo-32-caracteres-muy-segura-cambiar-en-produccion
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
```

**⚠️ IMPORTANTE:** Genera una clave segura única para producción:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

#### 🌐 CORS

```env
CORS_ORIGINS=https://tu-frontend.vercel.app,https://tu-dominio.com
```

**Nota:** Agrega las URLs de tu frontend separadas por comas.

#### 📧 Email (Brevo)

```env
EMAIL_PROVIDER=smtp
EMAIL_FROM_ADDRESS=noreply@tu-dominio.com
EMAIL_FROM_NAME=MecánicoYa

# SMTP Configuration
BREVO_SMTP_HOST=smtp-relay.brevo.com
BREVO_SMTP_PORT=587
BREVO_SMTP_USER=tu-usuario-brevo
BREVO_SMTP_PASSWORD=tu-password-brevo

# Frontend URL
FRONTEND_URL=https://tu-frontend.vercel.app
```

#### 🔔 Firebase Push Notifications (OPCIÓN 1 - RECOMENDADA)

**Método: Variable de Entorno JSON**

1. Abre tu archivo `mecanicoya-xxxxx-firebase-adminsdk-xxxxx.json`
2. Copia TODO el contenido del archivo
3. Minimiza el JSON en una sola línea (puedes usar [jsonformatter.org](https://jsonformatter.org/json-minify))
4. Agrega la variable en Railway:

```env
FIREBASE_CREDENTIALS_JSON={"type":"service_account","project_id":"mecanicoya-xxxxx","private_key_id":"xxxxx","private_key":"-----BEGIN PRIVATE KEY-----\nxxxxx\n-----END PRIVATE KEY-----\n","client_email":"firebase-adminsdk-xxxxx@mecanicoya-xxxxx.iam.gserviceaccount.com","client_id":"xxxxx","auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token","auth_provider_x509_cert_url":"https://www.googleapis.com/oauth2/v1/certs","client_x509_cert_url":"https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk-xxxxx%40mecanicoya-xxxxx.iam.gserviceaccount.com"}
```

**⚠️ IMPORTANTE:** 
- Asegúrate de que el JSON esté en UNA SOLA LÍNEA
- Mantén los saltos de línea `\n` en la clave privada
- NO agregues comillas extras alrededor del JSON

5. Agrega también:

```env
FIREBASE_PROJECT_ID=mecanicoya-xxxxx
PUSH_NOTIFICATIONS_ENABLED=true
```

#### 🔔 Firebase Push Notifications (OPCIÓN 2 - ALTERNATIVA)

**Método: Railway Volume (más complejo)**

Si prefieres usar un archivo en lugar de variable de entorno:

1. En Railway, ve a tu servicio > Settings > Volumes
2. Crea un nuevo volumen:
   - Mount Path: `/app/credentials`
3. Sube tu archivo JSON al volumen
4. Configura la variable:

```env
FIREBASE_SERVICE_ACCOUNT_PATH=/app/credentials/firebase-service-account.json
FIREBASE_PROJECT_ID=mecanicoya-xxxxx
PUSH_NOTIFICATIONS_ENABLED=true
```

**Nota:** La Opción 1 (JSON string) es más simple y recomendada.

#### 🔧 Configuración de Pool de Conexiones

```env
DB_POOL_SIZE=100
DB_MAX_OVERFLOW=20
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=3600
```

#### 🎯 Configuración de Entorno

```env
ENVIRONMENT=production
DEBUG=false
```

#### 🤖 Gemini AI (Opcional)

```env
GEMINI_API_KEY=tu-api-key-de-gemini
GEMINI_MODEL=gemini-2.0-flash
```

### 3. Configurar Build Settings

Railway debería detectar automáticamente que es un proyecto Python. Si no:

1. Ve a Settings > Build
2. Configura:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

### 4. Configurar Healthcheck (Opcional)

1. Ve a Settings > Healthcheck
2. Configura:
   - **Path:** `/api/v1/health`
   - **Timeout:** 30 segundos

### 5. Desplegar

1. Railway desplegará automáticamente cuando hagas push a tu rama principal
2. Puedes ver los logs en tiempo real en la pestaña "Deployments"
3. Una vez desplegado, Railway te dará una URL pública

## ✅ Verificar Despliegue

### 1. Verificar API

Visita: `https://tu-app.railway.app/api/v1/health`

Deberías ver:
```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T00:00:00Z",
  "version": "0.1.0"
}
```

### 2. Verificar Base de Datos

Visita: `https://tu-app.railway.app/api/v1/health/db`

Deberías ver:
```json
{
  "status": "healthy",
  "database": "connected"
}
```

### 3. Verificar Documentación

Visita: `https://tu-app.railway.app/docs`

Deberías ver la documentación interactiva de Swagger.

## 🔍 Troubleshooting

### Error: "Firebase initialization failed"

**Causa:** Credenciales de Firebase mal configuradas.

**Solución:**
1. Verifica que `FIREBASE_CREDENTIALS_JSON` esté en una sola línea
2. Verifica que los saltos de línea `\n` estén presentes en la clave privada
3. Verifica que no haya comillas extras
4. Prueba copiar el JSON directamente sin minificar

### Error: "Database connection failed"

**Causa:** URL de base de datos incorrecta o Supabase no permite la conexión.

**Solución:**
1. Verifica que `DATABASE_URL` sea correcta
2. Verifica que incluya `?sslmode=require` al final
3. En Supabase, ve a Settings > Database > Connection Pooling y verifica que esté habilitado

### Error: "CORS policy blocked"

**Causa:** Frontend no está en la lista de orígenes permitidos.

**Solución:**
1. Agrega la URL de tu frontend a `CORS_ORIGINS`
2. Asegúrate de incluir el protocolo (`https://`)
3. No incluyas trailing slash (`/`)

### Error: "JWT secret key too short"

**Causa:** `JWT_SECRET_KEY` no cumple con los requisitos de seguridad.

**Solución:**
1. Genera una nueva clave con al menos 32 caracteres
2. Usa el comando: `python -c "import secrets; print(secrets.token_urlsafe(32))"`

## 📊 Monitoreo

### Logs

Ver logs en tiempo real:
1. Ve a tu proyecto en Railway
2. Click en "Deployments"
3. Selecciona el deployment activo
4. Los logs aparecerán en tiempo real

### Métricas

Railway proporciona métricas automáticas:
- CPU usage
- Memory usage
- Network traffic
- Request count

## 🔄 Actualizaciones

Railway despliega automáticamente cuando:
1. Haces push a la rama principal de GitHub
2. Cambias variables de entorno (reinicia el servicio)

Para desplegar manualmente:
1. Ve a Deployments
2. Click en "Deploy"

## 💰 Costos

Railway ofrece:
- **Plan Hobby:** $5/mes + uso
- **Plan Pro:** $20/mes + uso

Costos aproximados para este proyecto:
- Pequeña escala: ~$5-10/mes
- Mediana escala: ~$20-30/mes

## 🔒 Seguridad

### Checklist de Seguridad

- [ ] `JWT_SECRET_KEY` es único y seguro (32+ caracteres)
- [ ] `CORS_ORIGINS` solo incluye dominios confiables
- [ ] `DEBUG=false` en producción
- [ ] `ENVIRONMENT=production`
- [ ] Credenciales de Firebase están en variable de entorno
- [ ] `.env` está en `.gitignore`
- [ ] Archivo JSON de Firebase NO está en el repositorio
- [ ] Base de datos usa SSL (`sslmode=require`)

## 📚 Recursos

- [Railway Docs](https://docs.railway.app/)
- [FastAPI Deployment](https://fastapi.tiangolo.com/deployment/)
- [Supabase Connection Pooling](https://supabase.com/docs/guides/database/connecting-to-postgres#connection-pooler)
- [Firebase Admin SDK](https://firebase.google.com/docs/admin/setup)

## 🆘 Soporte

Si tienes problemas:
1. Revisa los logs en Railway
2. Verifica las variables de entorno
3. Consulta la documentación de Railway
4. Revisa el README.md del proyecto
