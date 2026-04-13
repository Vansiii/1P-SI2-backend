"""Template base para emails con diseño profesional."""


def get_base_template(content: str, app_name: str = "Sistema de Emergencias Vehiculares") -> str:
    """
    Template base HTML para todos los emails.
    
    Args:
        content: Contenido HTML del email
        app_name: Nombre de la aplicación
        
    Returns:
        HTML completo con estilos y estructura base
    """
    return f"""
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{app_name}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333333;
            background-color: #f4f4f4;
        }}
        
        .email-container {{
            max-width: 600px;
            margin: 0 auto;
            background-color: #ffffff;
        }}
        
        .email-header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 30px 20px;
            text-align: center;
        }}
        
        .email-header h1 {{
            color: #ffffff;
            font-size: 24px;
            font-weight: 600;
            margin: 0;
        }}
        
        .email-body {{
            padding: 40px 30px;
        }}
        
        .email-body h2 {{
            color: #2c3e50;
            font-size: 22px;
            margin-bottom: 20px;
            font-weight: 600;
        }}
        
        .email-body p {{
            color: #555555;
            margin-bottom: 15px;
            font-size: 15px;
        }}
        
        .email-body ul {{
            margin: 15px 0;
            padding-left: 20px;
        }}
        
        .email-body li {{
            color: #555555;
            margin-bottom: 8px;
        }}
        
        .alert-box {{
            border-left: 4px solid;
            padding: 15px 20px;
            margin: 25px 0;
            border-radius: 4px;
        }}
        
        .alert-success {{
            background-color: #d4edda;
            border-color: #28a745;
            color: #155724;
        }}
        
        .alert-info {{
            background-color: #d1ecf1;
            border-color: #17a2b8;
            color: #0c5460;
        }}
        
        .alert-warning {{
            background-color: #fff3cd;
            border-color: #ffc107;
            color: #856404;
        }}
        
        .alert-danger {{
            background-color: #f8d7da;
            border-color: #dc3545;
            color: #721c24;
        }}
        
        .code-box {{
            background-color: #f8f9fa;
            border: 2px solid #007bff;
            border-radius: 8px;
            padding: 25px;
            text-align: center;
            margin: 25px 0;
        }}
        
        .code-box h1 {{
            color: #007bff;
            font-size: 42px;
            letter-spacing: 8px;
            margin: 0;
            font-weight: 700;
        }}
        
        .button {{
            display: inline-block;
            padding: 14px 30px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #ffffff !important;
            text-decoration: none;
            border-radius: 6px;
            font-weight: 600;
            margin: 20px 0;
            transition: transform 0.2s;
        }}
        
        .button:hover {{
            transform: translateY(-2px);
        }}
        
        .email-footer {{
            background-color: #f8f9fa;
            padding: 25px 30px;
            text-align: center;
            border-top: 1px solid #e9ecef;
        }}
        
        .email-footer p {{
            color: #6c757d;
            font-size: 13px;
            margin: 5px 0;
        }}
        
        .divider {{
            border: none;
            border-top: 1px solid #e9ecef;
            margin: 25px 0;
        }}
        
        @media only screen and (max-width: 600px) {{
            .email-body {{
                padding: 25px 20px;
            }}
            
            .email-header h1 {{
                font-size: 20px;
            }}
            
            .code-box h1 {{
                font-size: 36px;
                letter-spacing: 6px;
            }}
        }}
    </style>
</head>
<body>
    <div class="email-container">
        <div class="email-header">
            <h1>{app_name}</h1>
        </div>
        <div class="email-body">
            {content}
        </div>
        <div class="email-footer">
            <p>Este es un email automático, por favor no respondas.</p>
            <p>&copy; 2026 {app_name}. Todos los derechos reservados.</p>
        </div>
    </div>
</body>
</html>
"""


def get_text_base(content: str, app_name: str = "Sistema de Emergencias Vehiculares") -> str:
    """
    Template base de texto plano para todos los emails.
    
    Args:
        content: Contenido en texto plano
        app_name: Nombre de la aplicación
        
    Returns:
        Texto plano formateado
    """
    separator = "=" * 60
    return f"""
{separator}
{app_name}
{separator}

{content}

{separator}
Este es un email automático, por favor no respondas.
© 2026 {app_name}. Todos los derechos reservados.
{separator}
"""

