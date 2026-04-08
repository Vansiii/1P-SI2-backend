# Guía de Testing - Backend 1P-SI2

**Fecha:** Abril 2026  
**Estado:** ✅ Estructura de tests implementada

---

## 📋 Requisitos Previos

### **1. Instalar Dependencias**

```powershell
# Activar entorno virtual
.\.venv\Scripts\Activate.ps1

# Instalar dependencias de desarrollo
pip install -e ".[dev]"

# O si usas requirements
pip install -r requirements-dev.txt
```

### **2. Configurar Variables de Entorno**

Crear archivo `.env.test` (opcional):
```env
DATABASE_URL=sqlite+aiosqlite:///:memory:
ENVIRONMENT=testing
JWT_SECRET_KEY=test-secret-key-for-testing-only
```

---

## 🧪 Ejecutar Tests

### **Todos los Tests**

```powershell
# Ejecutar todos los tests
pytest

# Con output detallado
pytest -v

# Con cobertura
pytest --cov=app --cov-report=html
```

### **Tests por Categoría**

```powershell
# Tests unitarios del core
pytest tests/test_core/

# Tests de repositorios
pytest tests/test_repositories/

# Tests de servicios
pytest tests/test_services/

# Tests de API (integración)
pytest tests/test_api/
```

### **Tests Específicos**

```powershell
# Un archivo específico
pytest tests/test_core/test_security.py

# Una clase específica
pytest tests/test_core/test_security.py::TestPasswordHashing

# Un test específico
pytest tests/test_core/test_security.py::TestPasswordHashing::test_hash_password
```

### **Tests con Filtros**

```powershell
# Tests que contienen "password" en el nombre
pytest -k password

# Tests que NO contienen "slow"
pytest -k "not slow"

# Tests marcados con @pytest.mark.asyncio
pytest -m asyncio
```

---

## 📊 Cobertura de Código

### **Generar Reporte de Cobertura**

```powershell
# Generar reporte HTML
pytest --cov=app --cov-report=html

# Abrir reporte en navegador
start htmlcov/index.html

# Generar reporte en terminal
pytest --cov=app --cov-report=term-missing

# Generar reporte XML (para CI/CD)
pytest --cov=app --cov-report=xml
```

### **Verificar Cobertura Mínima**

```powershell
# Fallar si cobertura < 80%
pytest --cov=app --cov-fail-under=80
```

---

## 🎯 Estado Actual de Tests

### **✅ Tests Implementados**

#### **Core (100%)**
- ✅ `test_security.py` - 15 tests
  - Hash y verificación de passwords
  - Validación de fortaleza de passwords
  - Creación y decodificación de JWT
  - Generación y verificación de OTP
  
- ✅ `test_exceptions.py` - 18 tests
  - Todas las excepciones personalizadas
  - Códigos de error y status codes
  
- ✅ `test_responses.py` - 10 tests
  - Respuestas de éxito
  - Respuestas de error
  - Respuestas paginadas

#### **Repositories (Parcial)**
- ✅ `test_user_repository.py` - 10 tests
  - CRUD básico de usuarios
  - Búsqueda por email
  - Activación/desactivación

#### **Services (Parcial)**
- ✅ `test_auth_service.py` - 5 tests
  - Login exitoso
  - Login con credenciales inválidas
  - Login con 2FA
  - Logout

#### **API Integration (Parcial)**
- ✅ `test_health.py` - 5 tests
  - Health checks básicos y detallados
  - Probes de Kubernetes
  
- ✅ `test_auth.py` - 10 tests
  - Registro de usuarios
  - Login y logout
  - Gestión de perfil

### **⏳ Tests Pendientes**

#### **Repositories**
- [ ] `test_token_repository.py`
- [ ] `test_password_repository.py`
- [ ] `test_two_factor_repository.py`
- [ ] `test_audit_repository.py`

#### **Services**
- [ ] `test_registration_service.py`
- [ ] `test_profile_service.py`
- [ ] `test_token_service.py`
- [ ] `test_password_service.py`
- [ ] `test_two_factor_service.py`
- [ ] `test_audit_service.py`
- [ ] `test_notification_service.py`

#### **API Integration**
- [ ] `test_users_api.py`
- [ ] `test_tokens_api.py`
- [ ] `test_password_api.py`
- [ ] `test_two_factor_api.py`
- [ ] `test_audit_api.py`

#### **Models**
- [ ] `test_user_model.py`
- [ ] `test_relationships.py`
- [ ] `test_constraints.py`

#### **Schemas**
- [ ] `test_validation_schemas.py`
- [ ] `test_serialization.py`

---

## 🔧 Configuración de Tests

### **pytest.ini**

El archivo `pyproject.toml` contiene la configuración de pytest:

```toml
[tool.pytest.ini_options]
minversion = "8.0"
addopts = [
    "-ra",
    "--strict-markers",
    "--strict-config",
    "--cov=app",
    "--cov-report=term-missing",
]
testpaths = ["tests"]
asyncio_mode = "auto"
```

### **Fixtures Disponibles**

En `tests/conftest.py`:

- `test_settings` - Configuración de test
- `event_loop` - Event loop para tests async
- `async_engine` - Engine de base de datos async
- `db_session` - Sesión de base de datos
- `client` - TestClient de FastAPI
- `sample_client` - Usuario cliente de prueba
- `sample_workshop` - Taller de prueba
- `sample_technician` - Técnico de prueba
- `sample_admin` - Administrador de prueba
- `auth_headers` - Headers de autenticación
- `mock_email_service` - Mock del servicio de email

---

## 📝 Escribir Nuevos Tests

### **Estructura de Test**

```python
"""
Tests para [módulo].
"""
import pytest

from app.modules.[modulo].service import [Service]


class Test[Funcionalidad]:
    """Test [funcionalidad]."""
    
    @pytest.mark.asyncio
    async def test_[caso_exitoso](self, db_session):
        """Test [descripción del caso exitoso]."""
        # Arrange
        service = [Service](db_session)
        
        # Act
        result = await service.metodo()
        
        # Assert
        assert result is not None
    
    @pytest.mark.asyncio
    async def test_[caso_error](self, db_session):
        """Test [descripción del caso de error]."""
        # Arrange
        service = [Service](db_session)
        
        # Act & Assert
        with pytest.raises(Exception):
            await service.metodo_que_falla()
```

### **Mejores Prácticas**

1. **Usar fixtures** para setup común
2. **Nombrar tests descriptivamente**: `test_[accion]_[condicion]_[resultado]`
3. **Seguir patrón AAA**: Arrange, Act, Assert
4. **Un assert por test** (cuando sea posible)
5. **Tests independientes**: No depender del orden de ejecución
6. **Limpiar después**: Usar fixtures con yield para cleanup
7. **Mockear servicios externos**: Email, APIs externas, etc.

---

## 🚀 CI/CD Integration

### **GitHub Actions Example**

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.10'
    
    - name: Install dependencies
      run: |
        pip install -e ".[dev]"
    
    - name: Run tests
      run: |
        pytest --cov=app --cov-report=xml
    
    - name: Upload coverage
      uses: codecov/codecov-action@v3
```

---

## 🎯 Objetivos de Cobertura

### **Mínimos Requeridos**
- ✅ Core: 100% (COMPLETADO)
- ⏳ Repositories: >90% (actual: ~40%)
- ⏳ Services: >85% (actual: ~20%)
- ⏳ API Endpoints: >80% (actual: ~30%)
- ⏳ General: >80% (actual: ~60%)

### **Prioridades**
1. **Crítico**: Core, Security, Auth (100%)
2. **Alto**: Repositories, Services principales (>90%)
3. **Medio**: API endpoints, Schemas (>80%)
4. **Bajo**: Utils, Helpers (>70%)

---

## 🐛 Debugging Tests

### **Ejecutar con Debugger**

```powershell
# Con pdb
pytest --pdb

# Detener en primer fallo
pytest -x --pdb

# Ver print statements
pytest -s
```

### **Ver Logs**

```powershell
# Ver logs de aplicación
pytest --log-cli-level=DEBUG

# Ver logs de tests
pytest -v --log-cli-level=INFO
```

---

## 📚 Recursos

- [Pytest Documentation](https://docs.pytest.org/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [SQLAlchemy Testing](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#joining-a-session-into-an-external-transaction-such-as-for-test-suites)

---

**Última actualización:** Abril 2026  
**Mantenido por:** Equipo 1P-SI2