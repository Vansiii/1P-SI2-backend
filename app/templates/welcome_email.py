"""Template de email de bienvenida."""

from .email_base import get_base_template, get_text_base


def get_welcome_email_html(user_name: str, user_type: str, app_name: str) -> str:
    """
    Template HTML para email de bienvenida.
    
    Args:
        user_name: Nombre del usuario
        user_type: Tipo de usuario (Cliente, Taller, Técnico, Administrador)
        app_name: Nombre de la aplicación
        
    Returns:
        HTML completo del email
    """
    content = f"""
        <h2>¡Bienvenido a {app_name}!</h2>
        <p>Hola <strong>{user_name}</strong>,</p>
        <p>Tu cuenta de <strong>{user_type}</strong> ha sido creada exitosamente.</p>
        <p>Ya puedes acceder a todas las funcionalidades del sistema.</p>
        
        <div class="alert-box alert-success">
            <p style="margin: 0;"><strong>Próximos pasos:</strong></p>
            <ul style="margin: 10px 0;">
                <li>Completa tu perfil</li>
                <li>Configura tus preferencias</li>
                <li>Explora las funcionalidades disponibles</li>
            </ul>
        </div>
        
        <p>Si tienes alguna pregunta, no dudes en contactarnos.</p>
    """
    
    return get_base_template(content, app_name)


def get_welcome_email_text(user_name: str, user_type: str, app_name: str) -> str:
    """
    Template de texto plano para email de bienvenida.
    
    Args:
        user_name: Nombre del usuario
        user_type: Tipo de usuario
        app_name: Nombre de la aplicación
        
    Returns:
        Texto plano del email
    """
    content = f"""
¡Bienvenido a {app_name}!

Hola {user_name},

Tu cuenta de {user_type} ha sido creada exitosamente.

Ya puedes acceder a todas las funcionalidades del sistema.

Próximos pasos:
- Completa tu perfil
- Configura tus preferencias
- Explora las funcionalidades disponibles

Si tienes alguna pregunta, no dudes en contactarnos.
"""
    
    return get_text_base(content, app_name)

