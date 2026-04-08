# Validación de Tipo de Usuario para Acceso Web

## 🔍 Análisis Actual

### ✅ Estado: IMPLEMENTADO EN BACKEND

**Validación implementada en:** `app/modules/auth/services.py` - Método `AuthService.login()`

La validación restringe el acceso web solo a:
- ✅ Talleres (WORKSHOP)
- ✅ Técnicos (TECHNICIAN)  
- ✅ Administradores (ADMINISTRATOR)

**Los clientes (CLIENT) NO pueden iniciar sesión en la aplicación web.**

---

## 📊 Tipos de Usuario en el Sistema

```python
# app/core/constants.py
class UserType:
    CLIENT = "client"           # ❌ NO debe acceder a web
    WORKSHOP = "workshop"       # ✅ Debe acceder a web
    TECHNICIAN = "technician"   # ✅ Debe acceder a web
    ADMINISTRATOR = "administrator"  # ✅ Debe acceder a web
```

---

## 🎯 Requisito

**La aplicación web debe permitir login SOLO a:**
1. Talleres (workshop)
2. Técnicos (technician)
3. Administradores (administrator)

**Los clientes (client) deben usar exclusivamente la app móvil.**

---

## 🔧 Implementación Recomendada

### Opción 1: Validación en Backend (RECOMENDADO)

**Ventajas:**
- Seguridad centralizada
- No se puede bypassear desde el frontend
- Consistente en todas las plataformas

**Ubicación:** `app/modules/auth/services.py` - Método `AuthService.login()`

**Código a agregar:**

```python
# En AuthService.login(), después de verificar password (línea ~520)

# Verify password
if not verify_password(request.password, user.password_hash):
    # ... código existente de manejo de password incorrecto ...

# ✅ NUEVA VALIDACIÓN: Verificar tipo de usuario permitido para web
allowed_web_types = [UserType.WORKSHOP, UserType.TECHNICIAN, UserType.ADMINISTRATOR]
if user.user_type not in allowed_web_types:
    await self._record_login_attempt(
        email=email,
        success=False,
        ip_address=ip_address,
        user_agent=user_agent,
        user_id=user.id,
        failure_reason="unauthorized_user_type",
    )
    await self.session.commit()
    
    logger.warning(
        "Login attempt from unauthorized user type",
        user_id=user.id,
        user_type=user.user_type,
        email=email
    )
    
    raise InvalidCredentialsException(
        message="Este tipo de usuario no tiene acceso a la plataforma web. Por favor, usa la aplicación móvil.",
        details={
            "user_type": user.user_type,
            "allowed_types": allowed_web_types,
        }
    )

# Successful login clears stale block marker and records attempt.
await self._record_login_attempt(
    # ... resto del código existente ...
```

**Excepción personalizada (opcional):**

```python
# En app/core/exceptions.py

class UnauthorizedUserTypeException(AppException):
    """Exception raised when user type is not allowed for this platform."""
    
    def __init__(
        self,
        user_type: str,
        allowed_types: list[str],
        message: str = "Tipo de usuario no autorizado para esta plataforma"
    ):
        super().__init__(
            message=message,
            code="UNAUTHORIZED_USER_TYPE",
            status_code=403,
            details={
                "user_type": user_type,
                "allowed_types": allowed_types,
            }
        )
```

---

### Opción 2: Validación en Frontend (COMPLEMENTARIA)

**Ventajas:**
- Mejor UX (mensaje inmediato)
- Reduce llamadas innecesarias al backend

**Desventajas:**
- Se puede bypassear
- Debe usarse JUNTO con validación backend

**Ubicación:** `1P-SI2-frontend/src/app/core/services/auth.service.ts`

**Código a agregar:**

```typescript
// En AuthService.login(), después de recibir respuesta exitosa

login(loginRequest: LoginRequest): Observable<LoginResult> {
  return this.httpClient
    .post<ApiResponse<{
      user?: AppUserProfile;
      tokens?: Omit<AuthTokenResponse, 'user'>;
      requires_2fa?: boolean;
      user_type?: string;
      message?: string;
    }>>(`${this.apiBaseUrl}/auth/login`, loginRequest)
    .pipe(
      map((response) => {
        // Check if it's a 2FA challenge
        if (response.data.requires_2fa) {
          return {
            requires_2fa: true,
            email: loginRequest.email,
            message: response.data.message ?? 'Se requiere verificacion 2FA para completar el ingreso.',
          } as const;
        }

        // Check if we have tokens in the response
        if (response.data.tokens && response.data.user) {
          // ✅ NUEVA VALIDACIÓN: Verificar tipo de usuario
          const allowedWebTypes = ['workshop', 'technician', 'administrator', 'admin'];
          const userType = response.data.user.user_type || response.data.user.role || '';
          
          if (!allowedWebTypes.includes(userType.toLowerCase())) {
            throw new Error(
              'Este tipo de usuario no tiene acceso a la plataforma web. Por favor, usa la aplicación móvil.'
            );
          }

          const authResponse: AuthTokenResponse = {
            ...response.data.tokens,
            user: response.data.user,
          };
          this.persistSession(authResponse);
          return {
            requires_2fa: false,
            tokens: authResponse,
          } as const;
        }

        throw new Error('Respuesta de autenticacion no reconocida.');
      })
    );
}
```

---

### Opción 3: Guard de Ruta (COMPLEMENTARIA)

**Ventajas:**
- Protege rutas privadas
- Previene acceso directo por URL

**Ubicación:** `1P-SI2-frontend/src/app/core/guards/user-type.guard.ts` (nuevo archivo)

**Código:**

```typescript
import { inject } from '@angular/core';
import { Router, CanActivateFn } from '@angular/router';
import { AuthService } from '../services/auth.service';

export const userTypeGuard: CanActivateFn = (route, state) => {
  const authService = inject(AuthService);
  const router = inject(Router);
  
  const user = authService.user();
  
  if (!user) {
    router.navigate(['/auth']);
    return false;
  }
  
  const allowedTypes = ['workshop', 'technician', 'administrator', 'admin'];
  const userType = (user.user_type || user.role || '').toLowerCase();
  
  if (!allowedTypes.includes(userType)) {
    // Usuario autenticado pero tipo no permitido
    authService.logout().subscribe();
    router.navigate(['/auth'], {
      queryParams: { 
        error: 'unauthorized_type',
        message: 'Este tipo de usuario no tiene acceso a la plataforma web'
      }
    });
    return false;
  }
  
  return true;
};
```

**Uso en rutas:**

```typescript
// En app.routes.ts
import { userTypeGuard } from './core/guards/user-type.guard';

export const routes: Routes = [
  {
    path: 'dashboard',
    component: DashboardPageComponent,
    canActivate: [authGuard, userTypeGuard], // ✅ Agregar guard
  },
  {
    path: 'profile',
    component: ProfilePageComponent,
    canActivate: [authGuard, userTypeGuard], // ✅ Agregar guard
  },
  // ... otras rutas privadas
];
```

---

## 📝 Recomendación Final

**Implementar las 3 opciones en este orden:**

1. ✅ **Opción 1 (Backend)** - OBLIGATORIO
   - Seguridad real
   - No se puede bypassear
   
2. ✅ **Opción 2 (Frontend)** - RECOMENDADO
   - Mejor UX
   - Validación temprana
   
3. ✅ **Opción 3 (Guard)** - RECOMENDADO
   - Protección de rutas
   - Previene acceso directo

---

## 🧪 Testing

### Test Backend

```python
# tests/test_api/test_auth.py

@pytest.mark.asyncio
async def test_client_cannot_login_to_web(db_session):
    """Test that clients cannot login to web platform."""
    # Arrange
    auth_service = AuthService(db_session)
    
    # Create a client user
    client = Client(
        email="client@test.com",
        password_hash=hash_password("SecurePass123!"),
        user_type=UserType.CLIENT,
        is_active=True,
        direccion="Test Address",
        ci="12345678",
        fecha_nacimiento=date(1990, 1, 1)
    )
    db_session.add(client)
    await db_session.commit()
    
    # Act & Assert
    with pytest.raises(InvalidCredentialsException) as exc_info:
        await auth_service.login(
            LoginRequest(email="client@test.com", password="SecurePass123!"),
            ip_address="127.0.0.1"
        )
    
    assert "aplicación móvil" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_workshop_can_login_to_web(db_session):
    """Test that workshops can login to web platform."""
    # Arrange
    auth_service = AuthService(db_session)
    
    # Create a workshop user
    workshop = Workshop(
        email="workshop@test.com",
        password_hash=hash_password("SecurePass123!"),
        user_type=UserType.WORKSHOP,
        is_active=True,
        workshop_name="Test Workshop",
        owner_name="Owner Name",
        latitude=-17.3935,
        longitude=-66.1570,
        coverage_radius_km=10
    )
    db_session.add(workshop)
    await db_session.commit()
    
    # Act
    user, token_response = await auth_service.login(
        LoginRequest(email="workshop@test.com", password="SecurePass123!"),
        ip_address="127.0.0.1"
    )
    
    # Assert
    assert user is not None
    assert user.user_type == UserType.WORKSHOP
    assert token_response.access_token is not None
```

### Test Frontend

```typescript
// auth.service.spec.ts

it('should reject client user type', (done) => {
  const loginRequest = { email: 'client@test.com', password: 'pass123' };
  const mockResponse = {
    data: {
      user: { id: 1, email: 'client@test.com', user_type: 'client' },
      tokens: { access_token: 'token', refresh_token: 'refresh' }
    }
  };

  authService.login(loginRequest).subscribe({
    next: () => fail('Should have thrown error'),
    error: (error) => {
      expect(error.message).toContain('aplicación móvil');
      done();
    }
  });

  const req = httpMock.expectOne(`${environment.apiBaseUrl}/auth/login`);
  req.flush(mockResponse);
});
```

---

## 📋 Checklist de Implementación

- [x] Agregar validación en `AuthService.login()` (backend) ✅ **COMPLETADO**
- [ ] Agregar excepción `UnauthorizedUserTypeException` (opcional)
- [ ] Agregar validación en `AuthService.login()` (frontend) - RECOMENDADO
- [ ] Crear `userTypeGuard` (frontend) - RECOMENDADO
- [ ] Aplicar guard a rutas privadas - RECOMENDADO
- [ ] Agregar tests backend
- [ ] Agregar tests frontend
- [ ] Actualizar documentación de API
- [ ] Probar flujo completo manualmente

---

## 🎯 Resultado Esperado

Después de implementar:

1. **Cliente intenta login en web:**
   ```
   ❌ Error 403: "Este tipo de usuario no tiene acceso a la plataforma web. 
                  Por favor, usa la aplicación móvil."
   ```

2. **Taller/Técnico/Admin intenta login en web:**
   ```
   ✅ Login exitoso → Dashboard
   ```

3. **Cliente intenta acceder directamente a /dashboard:**
   ```
   ❌ Redirigido a /auth con mensaje de error
   ```
