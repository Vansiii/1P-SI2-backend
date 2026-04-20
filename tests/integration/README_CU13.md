# Tests de Integración CU13: Reasignación Automática

Este documento describe cómo ejecutar los tests de integración para el CU13 (Reasignación Automática de Taller por Rechazo o Inactividad).

## 📋 Requisitos Previos

### 1. Backend en Ejecución

El backend debe estar corriendo en `http://127.0.0.1:8000`:

```powershell
# Desde la carpeta 1P-SI2-backend
uvicorn app.main:app --reload
```

Verifica que esté corriendo:
```powershell
curl http://127.0.0.1:8000/health
```

### 2. Tokens de Autenticación

Necesitas obtener tokens JWT válidos para:
- **Administrador**: Usuario con permisos de administración
- **Cliente**: Usuario cliente que puede crear incidentes

#### Cómo Obtener Tokens

**Opción A: Usando el endpoint de login**

```powershell
# Login como administrador
$adminResponse = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/auth/login" -Method POST -Body (@{
    email = "admin@example.com"
    password = "tu_password"
} | ConvertTo-Json) -ContentType "application/json"

$env:INTEGRATION_ADMIN_TOKEN = $adminResponse.data.access_token

# Login como cliente
$clientResponse = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/auth/login" -Method POST -Body (@{
    email = "cliente@example.com"
    password = "tu_password"
} | ConvertTo-Json) -ContentType "application/json"

$env:INTEGRATION_CLIENT_TOKEN = $clientResponse.data.access_token
```

**Opción B: Desde la documentación interactiva**

1. Abre http://127.0.0.1:8000/docs
2. Usa el endpoint `/api/v1/auth/login` para obtener tokens
3. Copia los tokens y configúralos como variables de entorno

### 3. Configurar Variables de Entorno

```powershell
# Configurar tokens
$env:INTEGRATION_ADMIN_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
$env:INTEGRATION_CLIENT_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

# Habilitar tests de integración
$env:RUN_INTEGRATION_TESTS = "1"

# URL del backend (opcional, default: http://127.0.0.1:8000)
$env:INTEGRATION_BASE_URL = "http://127.0.0.1:8000"
```

## 🚀 Ejecutar Tests

### Opción 1: Script Automatizado (Recomendado)

```powershell
# Desde la carpeta 1P-SI2-backend
.\scripts\run_cu13_tests.ps1
```

Este script:
- ✅ Verifica que el backend esté corriendo
- ✅ Verifica que las variables de entorno estén configuradas
- ✅ Ejecuta todos los tests de CU13
- ✅ Muestra resultados detallados
- ✅ Limpia datos de prueba automáticamente

### Opción 2: Pytest Directo

```powershell
# Ejecutar todos los tests de CU13
pytest tests/integration/test_cu13_reasignacion.py -v

# Ejecutar un test específico
pytest tests/integration/test_cu13_reasignacion.py::test_scenario_01_asignacion_inicial_exitosa -v

# Ejecutar con más detalle
pytest tests/integration/test_cu13_reasignacion.py -v --tb=long

# Ejecutar y detener en el primer fallo
pytest tests/integration/test_cu13_reasignacion.py -v -x
```

## 📊 Escenarios de Testing

Los tests cubren 8 escenarios principales:

### 1. **Asignación Inicial Exitosa**
- ✅ Crear incidente
- ✅ Asignar automáticamente
- ✅ Verificar asignación al taller más cercano

### 2. **Rechazo y Reasignación**
- ✅ Asignación inicial
- ✅ Rechazo explícito del taller
- ✅ Reasignación automática a otro taller

### 3. **Múltiples Rechazos Consecutivos**
- ✅ Asignación inicial
- ✅ Múltiples rechazos
- ✅ Intentos con diferentes talleres

### 4. **Exclusión de Talleres Rechazados**
- ✅ Verificar que talleres que rechazaron no reciben nuevas asignaciones
- ✅ Validar lógica de exclusión

### 5. **Scoring con Penalización**
- ✅ Verificar que el scoring considera historial de rechazos
- ✅ Talleres con más rechazos tienen menor score

### 6. **Recálculo Dinámico de Candidatos**
- ✅ Verificar que cada intento recalcula candidatos
- ✅ Datos siempre actualizados

### 7. **Estadísticas de Asignación**
- ✅ Obtener estadísticas del sistema
- ✅ Verificar métricas de asignación

### 8. **Historial Completo de Asignación**
- ✅ Obtener historial de intentos
- ✅ Verificar información completa de cada intento

## 🧹 Limpieza de Datos

Los tests **limpian automáticamente** todos los datos de prueba al finalizar:
- ✅ Incidentes creados
- ✅ Talleres de prueba
- ✅ Técnicos de prueba
- ✅ Vehículos de prueba

**No es necesario limpiar manualmente la base de datos.**

## 📝 Estructura de Datos de Prueba

Los tests crean automáticamente:

### Talleres (3)
- **Taller A**: Cercano, especialidades: bateria, llanta, motor
- **Taller B**: Medio, especialidades: bateria, electrico
- **Taller C**: Lejano, especialidades: motor, llanta

### Técnicos (3)
- **Técnico A**: Taller A, especialidades: bateria, llanta
- **Técnico B**: Taller B, especialidades: bateria, electrico
- **Técnico C**: Taller C, especialidades: motor, llanta

### Vehículo (1)
- **TEST999**: Toyota Corolla 2020

### Incidentes (8)
- Uno por cada escenario de testing

## 🔍 Verificar Resultados

### Logs del Backend

Mientras los tests se ejecutan, puedes ver los logs del backend para observar:
- Asignaciones automáticas
- Cálculo de scores
- Exclusión de talleres
- Reasignaciones

### Base de Datos

Puedes consultar las tablas durante la ejecución:

```sql
-- Ver intentos de asignación
SELECT * FROM assignment_attempts ORDER BY attempted_at DESC LIMIT 10;

-- Ver rechazos de talleres
SELECT * FROM rechazos_taller ORDER BY created_at DESC LIMIT 10;

-- Ver incidentes de prueba
SELECT * FROM incidentes WHERE descripcion LIKE '%Test%' ORDER BY created_at DESC;
```

## ⚠️ Troubleshooting

### Error: "Backend is not reachable"
**Solución**: Asegúrate de que el backend esté corriendo en http://127.0.0.1:8000

```powershell
uvicorn app.main:app --reload
```

### Error: "Missing integration variables"
**Solución**: Configura las variables de entorno con tokens válidos

```powershell
$env:INTEGRATION_ADMIN_TOKEN = "tu_token"
$env:INTEGRATION_CLIENT_TOKEN = "tu_token"
$env:RUN_INTEGRATION_TESTS = "1"
```

### Error: "Failed to create workshop"
**Solución**: Verifica que el token de administrador tenga permisos correctos

### Error: "No available workshops found"
**Solución**: Verifica que los talleres de prueba se crearon correctamente y están activos

### Tests fallan por timeout
**Solución**: Aumenta el timeout en las requests o verifica la velocidad de tu conexión

## 📚 Documentación Relacionada

- [CU13_REASIGNACION_AUTOMATICA.md](../../docs/CU13_REASIGNACION_AUTOMATICA.md) - Documentación completa del CU13
- [AUDITORIA_TECNICA.md](../../AUDITORIA_TECNICA.md) - Estado general del proyecto
- [CHECKLIST_IMPLEMENTACION.md](../../CHECKLIST_IMPLEMENTACION.md) - Checklist de implementación

## 🎯 Próximos Pasos

Después de ejecutar estos tests exitosamente:

1. **Implementar Sistema de Timeout Automático**
   - Background task para verificar timeouts
   - Reasignación automática tras timeout

2. **Implementar Notificación a Administrador**
   - Cuando no hay talleres disponibles
   - Requiere intervención manual

3. **Implementar Endpoint de Rechazo**
   - Permitir que talleres rechacen explícitamente
   - Activar reasignación automática

4. **Testing de Timeout**
   - Simular timeouts de asignación
   - Verificar reasignación automática

## 📞 Soporte

Si encuentras problemas ejecutando los tests:
1. Verifica los logs del backend
2. Revisa la documentación de CU13
3. Consulta la auditoría técnica para el estado actual
