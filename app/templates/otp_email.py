"""Template de email con código OTP para 2FA."""

from .email_base import get_base_template, get_text_base


def get_otp_email_html(user_name: str, otp_code: str, app_name: str) -> str:
    """
    Template HTML para email con código OTP.
    
    Args:
        user_name: Nombre del usuario
        otp_code: Código OTP de 6 dígitos
        app_name: Nombre de la aplicación
        
    Returns:
        HTML completo del email
    """
    content = f"""
        <h2>Código de Verificación (2FA)</h2>
        <p>Hola <strong>{user_name}</strong>,</p>
        <p>Tu código de verificación de dos factores es:</p>
        
        <div class="code-box">
            <h1>{otp_code}</h1>
        </div>
        
        <div class="alert-box alert-warning">
            <p style="margin: 0;"><strong>⚠️ Este código expirará en 5 minutos.</strong></p>
        </div>
        
        <p>Si no solicitaste este código, ignora este correo y asegúrate de que tu cuenta esté segura.</p>
        
        <div class="alert-box alert-info">
            <p style="margin: 0;"><strong>Consejo de seguridad:</strong></p>
            <p style="margin: 5px 0 0 0;">Nunca compartas este código con nadie. Nuestro equipo nunca te pedirá este código.</p>
        </div>
    """
    
    return get_base_template(content, app_name)


def get_otp_email_text(user_name: str, otp_code: str, app_name: str) -> str:
    """
    Template de texto plano para email con código OTP.
    
    Args:
        user_name: Nombre del usuario
        otp_code: Código OTP de 6 dígitos
        app_name: Nombre de la aplicación
        
    Returns:
        Texto plano del email
    """
    content = f"""
Código de Verificación (2FA)

Hola {user_name},

Tu código de verificación de dos factores es:

{otp_code}

⚠️ Este código expirará en 5 minutos.

Si no solicitaste este código, ignora este correo y asegúrate de que tu cuenta esté segura.

Consejo de seguridad:
Nunca compartas este código con nadie. Nuestro equipo nunca te pedirá este código.
"""
    
    return get_text_base(content, app_name)

