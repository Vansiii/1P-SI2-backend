"""Template de email de notificación de cuenta desbloqueada."""

from .email_base import get_base_template, get_text_base


def get_account_unlocked_email_html(user_name: str, app_name: str) -> str:
    """
    Template HTML para email de cuenta desbloqueada.
    
    Args:
        user_name: Nombre del usuario
        app_name: Nombre de la aplicación
        
    Returns:
        HTML completo del email
    """
    content = f"""
        <h2>Cuenta Desbloqueada</h2>
        <p>Hola <strong>{user_name}</strong>,</p>
        <p>Tu cuenta ha sido desbloqueada por un administrador.</p>
        
        <div class="alert-box alert-success">
            <p style="margin: 0;">✅ Ya puedes iniciar sesión normalmente.</p>
        </div>
        
        <div class="alert-box alert-info">
            <p style="margin: 0;"><strong>Recomendaciones de seguridad:</strong></p>
            <ul style="margin: 10px 0;">
                <li>Asegúrate de usar una contraseña segura</li>
                <li>Considera activar autenticación de dos factores (2FA)</li>
                <li>No compartas tus credenciales</li>
                <li>Revisa la actividad reciente de tu cuenta</li>
            </ul>
        </div>
        
        <div class="alert-box alert-warning">
            <p style="margin: 0;"><strong>⚠️ ¿No solicitaste este desbloqueo?</strong></p>
            <p style="margin: 5px 0 0 0;">Contacta con soporte inmediatamente.</p>
        </div>
    """
    
    return get_base_template(content, app_name)


def get_account_unlocked_email_text(user_name: str, app_name: str) -> str:
    """
    Template de texto plano para email de cuenta desbloqueada.
    
    Args:
        user_name: Nombre del usuario
        app_name: Nombre de la aplicación
        
    Returns:
        Texto plano del email
    """
    content = f"""
Cuenta Desbloqueada

Hola {user_name},

Tu cuenta ha sido desbloqueada por un administrador.

✅ Ya puedes iniciar sesión normalmente.

Recomendaciones de seguridad:
- Asegúrate de usar una contraseña segura
- Considera activar autenticación de dos factores (2FA)
- No compartas tus credenciales
- Revisa la actividad reciente de tu cuenta

⚠️ ¿No solicitaste este desbloqueo?
Contacta con soporte inmediatamente.
"""
    
    return get_text_base(content, app_name)

