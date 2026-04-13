"""Template de email de confirmación de cambio de contraseña."""

from .email_base import get_base_template, get_text_base


def get_password_changed_email_html(user_name: str, app_name: str) -> str:
    """
    Template HTML para email de confirmación de cambio de contraseña.
    
    Args:
        user_name: Nombre del usuario
        app_name: Nombre de la aplicación
        
    Returns:
        HTML completo del email
    """
    content = f"""
        <h2>Contraseña Actualizada</h2>
        <p>Hola <strong>{user_name}</strong>,</p>
        <p>Tu contraseña ha sido cambiada exitosamente.</p>
        
        <div class="alert-box alert-success">
            <p style="margin: 0;">✅ Por seguridad, todas tus sesiones activas han sido cerradas.</p>
        </div>
        
        <div class="alert-box alert-danger">
            <p style="margin: 0;"><strong>⚠️ ¿No fuiste tú?</strong></p>
            <p style="margin: 5px 0 0 0;">Si no realizaste este cambio, contacta inmediatamente con soporte.</p>
        </div>
        
        <p>Recomendaciones de seguridad:</p>
        <ul>
            <li>Usa contraseñas únicas para cada servicio</li>
            <li>Activa la autenticación de dos factores (2FA)</li>
            <li>No compartas tu contraseña con nadie</li>
        </ul>
    """
    
    return get_base_template(content, app_name)


def get_password_changed_email_text(user_name: str, app_name: str) -> str:
    """
    Template de texto plano para email de confirmación de cambio de contraseña.
    
    Args:
        user_name: Nombre del usuario
        app_name: Nombre de la aplicación
        
    Returns:
        Texto plano del email
    """
    content = f"""
Contraseña Actualizada

Hola {user_name},

Tu contraseña ha sido cambiada exitosamente.

✅ Por seguridad, todas tus sesiones activas han sido cerradas.

⚠️ ¿No fuiste tú?
Si no realizaste este cambio, contacta inmediatamente con soporte.

Recomendaciones de seguridad:
- Usa contraseñas únicas para cada servicio
- Activa la autenticación de dos factores (2FA)
- No compartas tu contraseña con nadie
"""
    
    return get_text_base(content, app_name)

