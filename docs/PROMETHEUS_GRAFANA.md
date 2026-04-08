# Configuración de Prometheus y Grafana

**Fecha:** 7 de abril de 2026  
**Versión:** 1.0

---

## 📊 Métricas Implementadas

### HTTP Requests
- `http_requests_total` - Total de requests HTTP (por método, endpoint, status)
- `http_request_duration_seconds` - Duración de requests (histograma)
- `http_requests_in_progress` - Requests en progreso (gauge)

### Autenticación
- `auth_attempts_total` - Total de intentos de autenticación
- `auth_failures_total` - Total de fallos de autenticación
- `auth_lockouts_total` - Total de cuentas bloqueadas

### Tokens
- `tokens_created_total` - Total de tokens creados
- `tokens_revoked_total` - Total de tokens revocados
- `tokens_active` - Número de tokens activos

### Base de Datos
- `db_query_duration_seconds` - Duración de queries (histograma)
- `db_connections_active` - Conexiones activas
- `db_connections_idle` - Conexiones idle

### Usuarios
- `users_registered_total` - Total de usuarios registrados
- `users_active` - Número de usuarios activos

### 2FA
- `two_factor_enabled_total` - Total de usuarios con 2FA
- `two_factor_verifications_total` - Total de verificaciones 2FA

### Emails
- `emails_sent_total` - Total de emails enviados
- `emails_failed_total` - Total de emails fallidos

### Rate Limiting
- `rate_limit_exceeded_total` - Total de requests bloqueados

### Errores
- `errors_total` - Total de errores
- `exceptions_total` - Total de excepciones

---

## 🔧 Configuración de Prometheus

### 1. Instalar Prometheus

```bash
# Windows (con Chocolatey)
choco install prometheus

# Linux
wget https://github.com/prometheus/prometheus/releases/download/v2.45.0/prometheus-2.45.0.linux-amd64.tar.gz
tar xvfz prometheus-*.tar.gz
cd prometheus-*
```

### 2. Configurar prometheus.yml

Crear archivo `prometheus.yml`:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s
  external_labels:
    monitor: '1p-si2-backend'

scrape_configs:
  - job_name: 'fastapi-backend'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/api/v1/metrics'
    scheme: 'http'
    basic_auth:
      username: 'admin'
      password: 'your_admin_password'
    scrape_interval: 10s
    scrape_timeout: 5s

  - job_name: 'fastapi-backend-public'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/api/v1/metrics/public'
    scheme: 'http'
    scrape_interval: 30s
```

### 3. Ejecutar Prometheus

```bash
# Windows
prometheus.exe --config.file=prometheus.yml

# Linux
./prometheus --config.file=prometheus.yml
```

Acceder a Prometheus UI: http://localhost:9090

---

## 📈 Configuración de Grafana

### 1. Instalar Grafana

```bash
# Windows (con Chocolatey)
choco install grafana

# Linux
sudo apt-get install -y grafana
```

### 2. Iniciar Grafana

```bash
# Windows
net start grafana

# Linux
sudo systemctl start grafana-server
sudo systemctl enable grafana-server
```

Acceder a Grafana: http://localhost:3000  
Credenciales por defecto: admin/admin

### 3. Agregar Data Source

1. Ir a Configuration → Data Sources
2. Click "Add data source"
3. Seleccionar "Prometheus"
4. Configurar:
   - Name: `1P-SI2 Backend`
   - URL: `http://localhost:9090`
   - Access: `Server`
5. Click "Save & Test"

### 4. Importar Dashboard

Crear dashboard con los siguientes paneles:

#### Panel 1: Request Rate
```promql
rate(http_requests_total[5m])
```

#### Panel 2: Request Duration (p95)
```promql
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))
```

#### Panel 3: Error Rate
```promql
rate(errors_total[5m])
```

#### Panel 4: Active Users
```promql
sum(users_active) by (user_type)
```

#### Panel 5: Auth Failures
```promql
rate(auth_failures_total[5m])
```

#### Panel 6: Database Connections
```promql
db_connections_active
db_connections_idle
```

#### Panel 7: Token Operations
```promql
rate(tokens_created_total[5m])
rate(tokens_revoked_total[5m])
```

#### Panel 8: Email Status
```promql
rate(emails_sent_total{status="success"}[5m])
rate(emails_sent_total{status="failure"}[5m])
```

---

## 🚨 Alertas Recomendadas

### 1. High Error Rate

```yaml
groups:
  - name: backend_alerts
    rules:
      - alert: HighErrorRate
        expr: rate(errors_total[5m]) > 0.05
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High error rate detected"
          description: "Error rate is {{ $value }} errors/sec"
```

### 2. High Response Time

```yaml
      - alert: HighResponseTime
        expr: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High response time detected"
          description: "P95 response time is {{ $value }}s"
```

### 3. Database Connection Pool Exhausted

```yaml
      - alert: DatabasePoolExhausted
        expr: db_connections_idle < 2
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Database connection pool almost exhausted"
          description: "Only {{ $value }} idle connections remaining"
```

### 4. High Auth Failure Rate

```yaml
      - alert: HighAuthFailureRate
        expr: rate(auth_failures_total[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High authentication failure rate"
          description: "Auth failure rate is {{ $value }} failures/sec"
```

### 5. Email Delivery Issues

```yaml
      - alert: EmailDeliveryIssues
        expr: rate(emails_failed_total[5m]) > 0.01
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Email delivery issues detected"
          description: "Email failure rate is {{ $value }} failures/sec"
```

---

## 🐳 Docker Compose

Para ejecutar Prometheus y Grafana con Docker:

```yaml
version: '3.8'

services:
  prometheus:
    image: prom/prometheus:latest
    container_name: prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
    restart: unless-stopped

  grafana:
    image: grafana/grafana:latest
    container_name: grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_USERS_ALLOW_SIGN_UP=false
    volumes:
      - grafana_data:/var/lib/grafana
    depends_on:
      - prometheus
    restart: unless-stopped

volumes:
  prometheus_data:
  grafana_data:
```

Ejecutar:

```bash
docker-compose up -d
```

---

## 📊 Queries PromQL Útiles

### Request Rate por Endpoint
```promql
sum(rate(http_requests_total[5m])) by (endpoint)
```

### Error Rate por Tipo
```promql
sum(rate(errors_total[5m])) by (error_type)
```

### Duración Promedio de Requests
```promql
rate(http_request_duration_seconds_sum[5m]) / rate(http_request_duration_seconds_count[5m])
```

### Usuarios Activos Total
```promql
sum(users_active)
```

### Tasa de Éxito de Autenticación
```promql
rate(auth_attempts_total{status="success"}[5m]) / rate(auth_attempts_total[5m])
```

### Tokens Activos por Tipo
```promql
sum(tokens_active) by (token_type)
```

### Rate Limit Excesos
```promql
sum(rate(rate_limit_exceeded_total[5m])) by (endpoint)
```

---

## 🔍 Troubleshooting

### Prometheus no puede scrape métricas

1. Verificar que el backend esté corriendo: `curl http://localhost:8000/api/v1/health`
2. Verificar autenticación: `curl -u admin:password http://localhost:8000/api/v1/metrics`
3. Revisar logs de Prometheus: `docker logs prometheus`

### Grafana no muestra datos

1. Verificar conexión a Prometheus: Configuration → Data Sources → Test
2. Verificar queries en Explore
3. Verificar rango de tiempo en dashboard

### Métricas no se actualizan

1. Verificar que el middleware de métricas esté activo
2. Verificar que haya tráfico en la aplicación
3. Revisar logs del backend

---

## 📚 Referencias

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [PromQL Basics](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [Grafana Dashboards](https://grafana.com/grafana/dashboards/)

---

**Última actualización:** 7 de abril de 2026
