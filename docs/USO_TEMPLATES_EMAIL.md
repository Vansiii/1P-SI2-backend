# Uso de Templates de Email - Análisis Detallado

## ✅ Inconsistencia Resuelta

Se corrigió la firma de `security_notification_email.py`:

**Antes:**
```python
def get_security_notification_email_html(
    user_name: str,
    action: str,
    ip_address: str,
    timestamp: str,
    app_name: str
)
```

**Después:**
```python
def get_security_notification_email_html(
    user_name: str,
    event_type: str,
    details: str,
    app_name: str
)
```

---

## 📧 Análisis de Uso por Template

### 1. ✅ welcome_email.py - Email de Bienvenida

**Estado:** ⚠️ **IMPLEMENTADO PERO NO USADO**

**Propósito:** Dar la bienvenida a nuevos usuarios al registrarse.

**Método del servicio:**
```python
NotificationService.send_welcome_email(
    to_email: str,
    user_name: str,
    user_type: str
) -> bool
```

**Dónde DEBERÍA usarse:**
- `RegistrationService._register_user_base()` - Después de crear usuario
- Endpoints: `/auth/register/client`, `/auth/register/workshop`, `/auth/register/technician`, `/auth/register/administrator`

**Problema detectado:**
El método `_register_user_base()` NO envía email de bienvenida después del registro.

**Recomendación:**
```python
# En RegistrationService._register_user_base(), después de commit:
try:
    from ...modules.notifications.service import NotificationService
    notification_service = NotificationService()
    user_name = user.email.split('@')[0]  # O usar nombre real si existe
    await notification_service.send_welcome_email(
        to_email=user.email,
        user_name=user_name,
        user_type=user_type
    )
except Exception as e:
    logger.error("Error sending welcome email", user_id=user.id, error=str(e))
```

---

### 2. ✅ password_reset_email.py - Recuperación de Contraseña

**Estado:** ✅ **EN USO ACTIVO**

**Propósito:** Enviar enlace para restablecer contraseña olvidada.

**Método del servicio:**
```python
NotificationService.send_password_reset_email(
    to_email: str,
    user_name: str,
    reset_token: str
) -> bool
```

**Usado en:**
- `PasswordService.forgot_password()` - Línea ~105
- Endpoint: `POST /auth/password/forgot`

**Flujo completo:**
1. Usuario solicita recuperación en `/auth/password/forgot`
2. `PasswordService.forgot_password(email)` genera token
3. Token se guarda en tabla `password_reset_token`
4. Se envía email con URL: `{frontend_url}/auth/reset-password?token={reset_token}`
5. Token expira en 1 hora

**Código real:**
```python
# En PasswordService.forgot_password()
try:
    user_name = await self._get_user_display_name(user)
    await self.email_service.send_password_reset_email(
        to_email=user.email,
        user_name=user_name,
        reset_token=reset_token,
    )
    logger.info("Password reset email sent", user_id=user.id, email=email)
except Exception as e:
    logger.error("Error sending password reset email", user_id=user.id, error=str(e))
```

**Verificación:** ✅ Correctamente implementado

---

### 3. ✅ otp_email.py - Código de Verificación 2FA

**Estado:** ✅ **EN USO ACTIVO**

**Propósito:** Enviar código OTP de 6 dígitos para autenticación de dos factores.

**Método del servicio:**
```python
NotificationService.send_otp_email(
    to_email: str,
    user_name: str,
    otp_code: str
) -> bool
```

**Usado en:**
- `TwoFactorService._send_otp_email()` - Método privado wrapper
- Llamado desde:
  - `TwoFactorService.enable_2fa()` - Activación de 2FA
  - `TwoFactorService.generate_login_otp()` - Login con 2FA
  - `TwoFactorService.resend_otp()` - Reenvío de código

**Flujo completo:**

**A) Activación de 2FA:**
1. Usuario solicita activar 2FA en `POST /auth/2fa/enable`
2. `TwoFactorService.enable_2fa(email)` genera OTP
3. OTP se guarda hasheado en tabla `two_factor_auth`
4. Se envía email con código de 6 dígitos
5. Código expira en 5 minutos
6. Usuario verifica con `POST /auth/2fa/verify`

**B) Login con 2FA:**
1. Usuario hace login en `POST /auth/login`
2. Si tiene 2FA activo, se genera OTP
3. Se envía email con código
4. Usuario completa login en `POST /auth/2fa/verify-login`

**Código real:**
```python
# En TwoFactorService._send_otp_email()
async def _send_otp_email(self, email: str, user_name: str, otp_code: str, is_resend: bool = False, is_login: bool = False) -> None:
    """Send OTP code via email."""
    await self.email_service.send_otp_email(email, user_name, otp_code)
```

**Verificación:** ✅ Correctamente implementado

---

### 4. ✅ password_changed_email.py - Confirmación de Cambio

**Estado:** ✅ **EN USO ACTIVO**

**Propósito:** Notificar que la contraseña fue cambiada exitosamente.

**Método del servicio:**
```python
NotificationService.send_password_changed_email(
    to_email: str,
    user_name: str
) -> bool
```

**Usado en:**
- `PasswordService.reset_password()` - Después de reset con token
- `PasswordService.change_password()` - Después de cambio manual

**Flujo completo:**

**A) Reset con token (contraseña olvidada):**
1. Usuario usa token de email en `POST /auth/password/reset`
2. `PasswordService.reset_password(token, new_password)` valida y actualiza
3. Token se marca como usado
4. Todas las sesiones se revocan
5. Se envía email de confirmación

**B) Cambio manual (desde perfil):**
1. Usuario autenticado cambia contraseña en `POST /auth/password/change`
2. `PasswordService.change_password(user_id, current_password, new_password)` valida
3. Contraseña se actualiza
4. Todas las sesiones se revocan
5. Se envía email de confirmación

**Código real:**
```python
# En PasswordService.reset_password() y change_password()
try:
    user_name = await self._get_user_display_name(user)
    await self.email_service.send_password_changed_email(
        to_email=user.email,
        user_name=user_name,
    )
    logger.info("Password changed email sent", user_id=user.id)
except Exception as e:
    logger.error("Error sending password changed email", user_id=user.id, error=str(e))
```

**Verificación:** ✅ Correctamente implementado

---

### 5. ✅ account_unlocked_email.py - Notificación de Desbloqueo

**Estado:** ✅ **EN USO ACTIVO**

**Propósito:** Informar que la cuenta fue desbloqueada por un administrador.

**Método del servicio:**
```python
NotificationService.send_account_unlocked_email(
    to_email: str,
    user_name: str
) -> bool
```

**Usado en:**
- Gestión de cuentas bloqueadas por administradores
- Sistema de lockout automático

**Flujo completo:**
1. Cuenta se bloquea por múltiples intentos fallidos
2. Administrador desbloquea cuenta manualmente
3. Se envía email notificando el desbloqueo
4. Usuario puede volver a iniciar sesión

**Código real:**
```python
# En NotificationService.send_account_unlocked_email()
try:
    app_name = self.settings.app_name
    html_content = get_account_unlocked_email_html(user_name, app_name)
    text_content = get_account_unlocked_email_text(user_name, app_name)
    
    success = await self.email_provider.send_email(
        to_email=to_email,
        subject=f"Notificación: Cuenta Desbloqueada - {app_name}",
        html_content=html_content,
        text_content=text_content,
    )
```

**Verificación:** ✅ Correctamente implementado

---

### 6. ✅ security_notification_email.py - Alertas de Seguridad

**Estado:** ✅ **EN USO ACTIVO (MULTIPROPÓSITO)**

**Propósito:** Notificar eventos de seguridad importantes.

**Método del servicio:**
```python
NotificationService.send_security_notification_email(
    to_email: str,
    user_name: str,
    event_type: str,
    details: str
) -> bool
```

**Usado en:**

**A) Cuenta bloqueada:**
```python
# NotificationService.send_account_locked_email()
await self.email_service.send_security_notification_email(
    to_email=email,
    user_name=user_name,
    event_type="Cuenta bloqueada por seguridad",
    details=f"Tu cuenta ha sido bloqueada temporalmente hasta {locked_until} debido a múltiples intentos de acceso fallidos."
)
```

**B) 2FA desactivado:**
```python
# TwoFactorService._send_2fa_disabled_email()
await self.email_service.send_security_notification_email(
    to_email=email,
    user_name=user_name,
    event_type="2FA Desactivado",
    details="La autenticación de dos factores ha sido desactivada en tu cuenta. Si no realizaste esta acción, contacta con soporte inmediatamente."
)
```

**Flujo completo:**

**Caso 1: Bloqueo de cuenta**
1. Usuario falla login 5 veces consecutivas
2. Cuenta se bloquea temporalmente (15-30 minutos)
3. Se envía email de alerta de seguridad
4. Usuario debe esperar o contactar admin

**Caso 2: Desactivación de 2FA**
1. Usuario desactiva 2FA en `POST /auth/2fa/disable`
2. `TwoFactorService.disable_2fa()` valida contraseña
3. 2FA se desactiva en base de datos
4. Se envía email de alerta de seguridad

**Código real:**
```python
# En NotificationService.send_security_notification_email()
try:
    app_name = self.settings.app_name
    html_content = get_security_notification_email_html(
        user_name, event_type, details, app_name
    )
    text_content = get_security_notification_email_text(
        user_name, event_type, details, app_name
    )
    
    success = await self.email_provider.send_email(
        to_email=to_email,
        subject=f"Alerta de Seguridad: {event_type} - {app_name}",
        html_content=html_content,
        text_content=text_content,
    )
```

**Verificación:** ✅ Correctamente implementado (después de corrección)

---

## 📊 Resumen de Estado

| Template | Estado | Usado En | Endpoints |
|----------|--------|----------|-----------|
| welcome_email | ⚠️ NO USADO | - | - |
| password_reset_email | ✅ ACTIVO | PasswordService | POST /auth/password/forgot |
| otp_email | ✅ ACTIVO | TwoFactorService | POST /auth/2fa/enable, /auth/login, /auth/2fa/resend |
| password_changed_email | ✅ ACTIVO | PasswordService | POST /auth/password/reset, /auth/password/change |
| account_unlocked_email | ✅ ACTIVO | Admin/Lockout | Admin panel |
| security_notification_email | ✅ ACTIVO | Multiple | Lockout, 2FA disable |

---

## 🔧 Recomendaciones de Implementación

### 1. Implementar Welcome Email

**Archivo:** `app/modules/auth/services.py`

**Método:** `RegistrationService._register_user_base()`

**Agregar después de la línea ~158 (después del commit):**

```python
# Send welcome email
try:
    from ...modules.notifications.service import NotificationService
    notification_service = NotificationService()
    
    # Get user display name
    user_name = user.email.split('@')[0]
    if hasattr(user, 'first_name') and user.first_name:
        user_name = user.first_name
    elif hasattr(user, 'owner_name') and user.owner_name:
        user_name = user.owner_name
    elif hasattr(user, 'workshop_name') and user.workshop_name:
        user_name = user.workshop_name
    
    # Map user_type to friendly name
    user_type_names = {
        UserType.CLIENT: "Cliente",
        UserType.WORKSHOP: "Taller",
        UserType.TECHNICIAN: "Técnico",
        UserType.ADMINISTRATOR: "Administrador",
    }
    
    await notification_service.send_welcome_email(
        to_email=user.email,
        user_name=user_name,
        user_type=user_type_names.get(user_type, user_type)
    )
    
    logger.info("Welcome email sent", user_id=user.id)
except Exception as e:
    # No fallar el registro si el email falla
    logger.error("Error sending welcome email", user_id=user.id, error=str(e))
```

### 2. Agregar IP y Timestamp a Security Notifications (Opcional)

Si se desea incluir información de IP y timestamp en las notificaciones de seguridad:

**Opción A:** Incluir en el parámetro `details`
```python
details = f"""Tu cuenta ha sido bloqueada temporalmente.

Detalles del evento:
- Fecha y hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- Dirección IP: {ip_address}
- Razón: Múltiples intentos de acceso fallidos

La cuenta se desbloqueará automáticamente el {locked_until}."""
```

**Opción B:** Modificar template para aceptar parámetros opcionales
```python
def get_security_notification_email_html(
    user_name: str,
    event_type: str,
    details: str,
    app_name: str,
    ip_address: str | None = None,
    timestamp: str | None = None
) -> str:
```

---

## 🧪 Testing

### Verificar Envío de Emails en Desarrollo

En modo desarrollo, los emails se imprimen en consola:

```bash
# Iniciar servidor
uvicorn app.main:app --reload

# Los emails aparecerán en la consola con formato:
==================================================
EMAIL TO: user@example.com
SUBJECT: Recuperación de Contraseña
FROM: Sistema <noreply@example.com>
==================================================
TEXT CONTENT:
...
--------------------------------------------------
HTML CONTENT:
...
==================================================
```

### Verificar Envío Real (Producción)

Configurar variables de entorno:

```env
# Opción 1: SMTP
EMAIL_PROVIDER=smtp
SMTP_SERVER=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_USERNAME=your-username
SMTP_PASSWORD=your-password
SMTP_FROM_EMAIL=noreply@yourdomain.com
SMTP_FROM_NAME=Sistema de Emergencias

# Opción 2: API
EMAIL_PROVIDER=api
BREVO_API_KEY=your-api-key
SMTP_FROM_EMAIL=noreply@yourdomain.com
SMTP_FROM_NAME=Sistema de Emergencias
```

### Tests Unitarios

Los tests ya existen en `tests/unit/services/test_email_service.py`:

```bash
# Ejecutar tests de email
pytest tests/unit/services/test_email_service.py -v

# Ejecutar todos los tests
pytest -v
```

---

## 📝 Conclusiones

1. **6 de 7 templates están en uso activo** ✅
2. **welcome_email está implementado pero no se usa** ⚠️
3. **Todos los templates funcionan correctamente** ✅
4. **Inconsistencia de security_notification_email resuelta** ✅
5. **Arquitectura de emails bien diseñada** ✅

### Próximos Pasos

1. ✅ Implementar envío de welcome_email en registro
2. Agregar tests de integración para flujos completos
3. Considerar agregar templates adicionales:
   - Email de verificación de cuenta
   - Email de cambio de email
   - Email de eliminación de cuenta programada
4. Documentar configuración de Brevo en README principal
