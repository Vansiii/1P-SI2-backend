# 📱 Configuración del Backend para Aplicación Móvil

## 🌐 Configuración de CORS

Para que la aplicación móvil pueda conectarse al backend, necesitas configurar CORS correctamente.

### Tu IP Local: `192.168.1.2`

---

## ⚙️ Configuración en .env

Edita el archivo `.env` en la raíz del proyecto backend:

```bash
# CORS Configuration - Agregar tu IP local
CORS_ORIGINS=http://localhost:4200,http://127.0.0.1:4200,http://192.168.1.2:4200,http://192.168.1.2:8000
```

### Explicación:
- `http://localhost:4200` - Frontend web en desarrollo local
- `http://127.0.0.1:4200` - Alternativa de localhost
- `http://192.168.1.2:4200` - Frontend web desde otros dispositivos
- `http://192.168.1.2:8000` - Aplicación móvil

### Para Desarrollo (Permitir Todo)

Si quieres permitir todas las conexiones durante desarrollo:

```bash
CORS_ORIGINS=*
```

⚠️ **IMPORTANTE**: Solo usar `*` en desarrollo, nunca en producción.

---

## 🚀 Iniciar el Backend

### Comando Correcto para Móvil

Para que dispositivos en tu red puedan conectarse, usa:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### ¿Por qué `--host 0.0.0.0`?

- `--host 127.0.0.1` (default) → Solo localhost puede conectarse
- `--host 0.0.0.0` → Todos los dispositivos en tu red pueden conectarse

---

## 🔥 Configuración del Firewall (Windows)

Si el móvil no puede conectarse, permite el puerto en el firewall:

### PowerShell (Como Administrador)

```powershell
New-NetFirewallRule -DisplayName "FastAPI Dev Server" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
```

### Verificar Regla Existente

```powershell
Get-NetFirewallRule -DisplayName "FastAPI Dev Server"
```

### Eliminar Regla (Si necesitas)

```powershell
Remove-NetFirewallRule -DisplayName "FastAPI Dev Server"
```

---

## ✅ Verificar Configuración

### 1. Verificar CORS en .env

```bash
cat .env | grep CORS_ORIGINS
```

Debería mostrar:
```
CORS_ORIGINS=http://localhost:4200,http://127.0.0.1:4200,http://192.168.1.2:4200,http://192.168.1.2:8000
```

### 2. Verificar que el Backend Esté Corriendo

Desde tu PC:
```bash
curl http://localhost:8000/api/v1/health
```

Desde tu red local:
```bash
curl http://192.168.1.2:8000/api/v1/health
```

Ambos deberían responder:
```json
{
  "status": "healthy",
  "timestamp": "..."
}
```

### 3. Verificar desde el Navegador del Móvil

Abre en el navegador de tu teléfono:
```
http://192.168.1.2:8000/docs
```

✅ Deberías ver la documentación de FastAPI

---

## 🔧 Configuración Completa del .env

Aquí está un ejemplo completo de `.env` configurado para móvil:

```bash
# Database Configuration
DATABASE_URL=postgresql://user:password@host:port/database

# JWT Configuration
JWT_SECRET_KEY=your-super-secret-key-min-32-characters-long
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# CORS Configuration - IMPORTANTE PARA MÓVIL
CORS_ORIGINS=http://localhost:4200,http://127.0.0.1:4200,http://192.168.1.2:4200,http://192.168.1.2:8000

# Email Configuration
EMAIL_PROVIDER=smtp
EMAIL_FROM_ADDRESS=noreply@example.com
EMAIL_FROM_NAME=Sistema de Emergencias Vehiculares

# Brevo SMTP
BREVO_SMTP_HOST=smtp-relay.brevo.com
BREVO_SMTP_PORT=587
BREVO_SMTP_USER=your-smtp-user
BREVO_SMTP_PASSWORD=your-smtp-password

# Frontend URL
FRONTEND_URL=http://localhost:4200

# Security Settings
PASSWORD_RESET_TOKEN_EXPIRE_MINUTES=60
OTP_EXPIRE_MINUTES=5
MAX_LOGIN_ATTEMPTS=5
LOCKOUT_DURATION_MINUTES=5

# Rate Limiting
RATE_LIMIT_WHITELIST_IPS=127.0.0.1,::1,192.168.1.2
RATE_LIMIT_ADMIN_MULTIPLIER=3
```

---

## 🐛 Solución de Problemas

### Error: "CORS policy: No 'Access-Control-Allow-Origin'"

**Causa**: CORS no está configurado correctamente.

**Solución**:
1. Verifica que tu IP esté en `CORS_ORIGINS`
2. Reinicia el backend después de cambiar `.env`
3. Para desarrollo, usa `CORS_ORIGINS=*`

### Error: "Connection refused"

**Causa**: Backend no acepta conexiones externas.

**Solución**:
```bash
# Asegúrate de usar --host 0.0.0.0
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Error: "Network unreachable"

**Causa**: Firewall bloqueando el puerto.

**Solución**:
```powershell
# Como Administrador
New-NetFirewallRule -DisplayName "FastAPI Dev Server" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
```

### Error: "Cannot connect from mobile"

**Checklist**:
- [ ] Backend corriendo con `--host 0.0.0.0`
- [ ] CORS configurado con tu IP
- [ ] Firewall permite puerto 8000
- [ ] Mismo WiFi en PC y móvil
- [ ] IP correcta en móvil (`192.168.1.2`)

---

## 📋 Checklist de Configuración

### Backend
- [ ] `.env` tiene tu IP en `CORS_ORIGINS`
- [ ] Backend inicia con `--host 0.0.0.0`
- [ ] Puerto 8000 abierto en firewall
- [ ] `/docs` accesible desde navegador del móvil

### Red
- [ ] PC y móvil en el mismo WiFi
- [ ] IP correcta (`192.168.1.2`)
- [ ] VPN desactivada
- [ ] Firewall configurado

### Móvil
- [ ] App configurada con `http://192.168.1.2:8000`
- [ ] Mismo WiFi que PC
- [ ] Depuración USB habilitada (si es físico)

---

## 🚀 Comandos Rápidos

### Iniciar Backend para Móvil
```bash
cd 1P-SI2-backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Verificar Conexión
```bash
# Desde PC
curl http://localhost:8000/api/v1/health

# Desde red local
curl http://192.168.1.2:8000/api/v1/health
```

### Ver Logs del Backend
Los logs mostrarán las peticiones del móvil:
```
INFO:     192.168.1.X:XXXXX - "POST /api/v1/auth/login HTTP/1.1" 200 OK
```

---

## 📝 Notas Importantes

### Desarrollo vs Producción

**Desarrollo** (Actual):
```bash
CORS_ORIGINS=http://localhost:4200,http://192.168.1.2:8000
# o
CORS_ORIGINS=*
```

**Producción**:
```bash
CORS_ORIGINS=https://tudominio.com,https://app.tudominio.com
```

### Seguridad

- ✅ Usar `*` solo en desarrollo
- ✅ En producción, especificar dominios exactos
- ✅ Usar HTTPS en producción
- ✅ No exponer el backend directamente en producción

---

## ✅ Verificación Final

1. **Backend corriendo**:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

2. **CORS configurado**:
   ```bash
   # .env contiene:
   CORS_ORIGINS=...,http://192.168.1.2:8000
   ```

3. **Accesible desde móvil**:
   ```
   http://192.168.1.2:8000/docs
   ```

4. **App móvil configurada**:
   ```dart
   baseUrl = 'http://192.168.1.2:8000'
   ```

---

**¡Listo para conectar el móvil!** 🎉
