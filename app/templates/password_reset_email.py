"""Template de email de recuperación de contraseña."""

from .email_base import get_base_template, get_text_base


def get_password_reset_email_html(
    user_name: str,
    reset_url: str,
    app_name: str
) -> str:
    """
    Template HTML para email de recuperación de contraseña.
    
    Args:
        user_name: Nombre del usuario
        reset_url: URL para restablecer contraseña
        app_name: Nombre de la aplicación
        
    Returns:
        HTML completo del email
    """
    content = f"""
        <h2>Recuperación de Contraseña</h2>
        <p>Hola <strong>{user_name}</strong>,</p>
        <p>Recibimos una solicitud para restablecer tu contraseña.</p>
        <p>Haz clic en el siguiente botón para crear una nueva contraseña:</p>
        
        <p style="text-align: center;">
            <a href="{reset_url}" class="button">Restablecer Contraseña</a>
        </p>
        
        <p>O copia y pega este enlace en tu navegador:</p>
        <p style="word-break: break-all; background-color: #f8f9fa; padding: 15px; border-radius: 4px; font-family: monospace; font-size: 13px;">
            {reset_url}
        </p>
        
        <div class="alert-box alert-warning">
            <p style="margin: 0;"><strong>⚠️ Este enlace expirará en 1 hora.</strong></p>
        </div>
        
        <p>Si no solicitaste este cambio, ignora este correo. Tu contraseña permanecerá sin cambios.</p>
    """
    
    return get_base_template(content, app_name)


def get_password_reset_email_text(
    user_name: str,
    reset_url: str,
    app_name: str
) -> str:
    """
    Template de texto plano para email de recuperación de contraseña.
    
    Args:
        user_name: Nombre del usuario
        reset_url: URL para restablecer contraseña
        app_name: Nombre de la aplicación
        
    Returns:
        Texto plano del email
    """
    content = f"""
Recuperación de Contraseña

Hola {user_name},

Recibimos una solicitud para restablecer tu contraseña.

Usa el siguiente enlace para crear una nueva contraseña:
{reset_url}

⚠️ Este enlace expirará en 1 hora.

Si no solicitaste este cambio, ignora este correo. Tu contraseña permanecerá sin cambios.
"""
    
    return get_text_base(content, app_name)

