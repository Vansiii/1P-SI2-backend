"""Template de email de notificación de seguridad."""

from .email_base import get_base_template, get_text_base


def get_security_notification_email_html(
    user_name: str,
    event_type: str,
    details: str,
    app_name: str
) -> str:
    """
    Template HTML para email de notificación de seguridad.
    
    Args:
        user_name: Nombre del usuario
        event_type: Tipo de evento (ej: "Cambio de contraseña", "Activación de 2FA")
        details: Detalles adicionales del evento
        app_name: Nombre de la aplicación
        
    Returns:
        HTML completo del email
    """
    content = f"""
        <h2>Notificación de Seguridad</h2>
        <p>Hola <strong>{user_name}</strong>,</p>
        <p>Se ha realizado una acción importante en tu cuenta:</p>
        
        <div class="alert-box alert-warning">
            <p style="margin: 0;"><strong>Evento:</strong> {event_type}</p>
            <p style="margin: 5px 0 0 0;">{details}</p>
        </div>
        
        <p><strong>¿No fuiste tú?</strong></p>
        <p>Si no reconoces esta actividad, te recomendamos tomar las siguientes medidas inmediatamente:</p>
        
        <ul>
            <li>Cambiar tu contraseña</li>
            <li>Revisar la actividad reciente de tu cuenta</li>
            <li>Activar autenticación de dos factores (2FA) si no lo has hecho</li>
            <li>Contactar con soporte si sospechas acceso no autorizado</li>
        </ul>
        
        <div class="alert-box alert-info">
            <p style="margin: 0;"><strong>Consejo de seguridad:</strong></p>
            <p style="margin: 5px 0 0 0;">Revisa regularmente la actividad de tu cuenta y mantén tu información de contacto actualizada.</p>
        </div>
    """
    
    return get_base_template(content, app_name)


def get_security_notification_email_text(
    user_name: str,
    event_type: str,
    details: str,
    app_name: str
) -> str:
    """
    Template de texto plano para email de notificación de seguridad.
    
    Args:
        user_name: Nombre del usuario
        event_type: Tipo de evento
        details: Detalles adicionales del evento
        app_name: Nombre de la aplicación
        
    Returns:
        Texto plano del email
    """
    content = f"""
Notificación de Seguridad

Hola {user_name},

Se ha realizado una acción importante en tu cuenta:

Evento: {event_type}
{details}

¿No fuiste tú?

Si no reconoces esta actividad, te recomendamos tomar las siguientes medidas inmediatamente:

- Cambiar tu contraseña
- Revisar la actividad reciente de tu cuenta
- Activar autenticación de dos factores (2FA) si no lo has hecho
- Contactar con soporte si sospechas acceso no autorizado

Consejo de seguridad:
Revisa regularmente la actividad de tu cuenta y mantén tu información de contacto actualizada.
"""
    
    return get_text_base(content, app_name)

