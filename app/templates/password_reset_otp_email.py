"""Template de email de recuperación de contraseña con código OTP para móvil."""

from .email_base import get_base_template, get_text_base


def get_password_reset_otp_email_html(
    user_name: str,
    otp_code: str,
    app_name: str
) -> str:
    """
    Template HTML para email de recuperación de contraseña con código OTP.
    
    Args:
        user_name: Nombre del usuario
        otp_code: Código OTP de 6 dígitos
        app_name: Nombre de la aplicación
        
    Returns:
        HTML completo del email
    """
    content = f"""
        <h2>Recuperación de Contraseña</h2>
        <p>Hola <strong>{user_name}</strong>,</p>
        <p>Recibimos una solicitud para restablecer tu contraseña desde la aplicación móvil.</p>
        <p>Tu código de verificación es:</p>
        
        <div class="code-box">
            <h1>{otp_code}</h1>
        </div>
        
        <p>Ingresa este código en la aplicación móvil para continuar con el proceso de recuperación.</p>
        
        <div class="alert-box alert-warning">
            <p style="margin: 0;"><strong>⚠️ Este código expirará en 10 minutos.</strong></p>
        </div>
        
        <p>Si no solicitaste este cambio, ignora este correo. Tu contraseña permanecerá sin cambios.</p>
        
        <div class="alert-box alert-info">
            <p style="margin: 0;"><strong>Consejo de seguridad:</strong></p>
            <p style="margin: 5px 0 0 0;">Nunca compartas este código con nadie. Nuestro equipo nunca te pedirá este código.</p>
        </div>
    """
    
    return get_base_template(content, app_name)


def get_password_reset_otp_email_text(
    user_name: str,
    otp_code: str,
    app_name: str
) -> str:
    """
    Template de texto plano para email de recuperación de contraseña con código OTP.
    
    Args:
        user_name: Nombre del usuario
        otp_code: Código OTP de 6 dígitos
        app_name: Nombre de la aplicación
        
    Returns:
        Texto plano del email
    """
    content = f"""
Recuperación de Contraseña

Hola {user_name},

Recibimos una solicitud para restablecer tu contraseña desde la aplicación móvil.

Tu código de verificación es:

{otp_code}

Ingresa este código en la aplicación móvil para continuar con el proceso de recuperación.

⚠️ Este código expirará en 10 minutos.

Si no solicitaste este cambio, ignora este correo. Tu contraseña permanecerá sin cambios.

Consejo de seguridad:
Nunca compartas este código con nadie. Nuestro equipo nunca te pedirá este código.
"""
    
    return get_text_base(content, app_name)
