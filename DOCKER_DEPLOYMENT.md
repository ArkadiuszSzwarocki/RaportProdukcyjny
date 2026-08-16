# Docker Deployment Guide

## Quick Start

### Prerequisites
- Docker & Docker Compose installed
- `.env` file configured (copy from `.env.example`)

### Basic Setup

```bash
# Copy configuration template
cp .env.example .env

# Edit .env with your settings
# Adjust: DB_PASSWORD, SECRET_KEY, INITIAL_ADMIN_PASSWORD

# Build and start services
docker-compose up -d

# View logs
docker-compose logs -f app

# Create admin user (if needed)
docker-compose exec app python scripts/add_admin.py
```

### Access Application
- **Web UI:** http://localhost:8082
- **Database:** localhost:3306 (MySQL)

---

## Docker Compose Architecture

### Services

#### 1. **db** (MySQL 8.0)
- **Role:** Database backend
- **Port:** 3306 (internal), configurable via `.env`
- **Volume:** `db_data` (persistent storage)
- **Health Check:** mysqladmin ping (10s interval)
- **Environment Variables:**
  - `MYSQL_ROOT_PASSWORD`
  - `MYSQL_DATABASE`
  - `MYSQL_USER`
  - `MYSQL_PASSWORD`

#### 2. **app** (Flask)
- **Role:** Application server  
- **Port:** 8082 (configurable via `.env`)
- **Build:** Multi-stage Dockerfile with security hardening
- **Volumes:**
  - `./logs` - Application logs
  - `./raporty` - Generated reports
  - `./config` - Configuration files
- **Health Check:** HTTP endpoint check (30s interval, 60s startup grace)
- **Dependencies:** Waits for `db` service to be healthy
- **Auto-restart:** unless-stopped

---

## Environment Configuration

### Key Variables (in `.env`)

```env
# Flask Settings
FLASK_ENV=production
SECRET_KEY=your-secret-key-here
INITIAL_ADMIN_PASSWORD=admin123

# Database
DB_HOST=db
DB_PORT=3306
DB_USER=raportprodukcyjny
DB_PASSWORD=your-db-password
DB_NAME=raportprodukcyjny

# Application Server
PORT=8082
HOST=0.0.0.0

# Timezone
TZ=Europe/Warsaw
```

### Copy from Template
```bash
cp .env.example .env
# Edit required values
```

---

## Docker Image Details

### Dockerfile Multi-Stage Build

**Stage 1: `builder`**
- Base: `python:3.11-slim`
- Installs dependencies via pip
- Minimizes final image size

**Stage 2: `main`** 
- Base: `python:3.11-slim`
- Copies pre-built dependencies from builder
- Creates non-root user: `appuser:1000`
- Runs application as unprivileged user
- Includes health check endpoint

### Security Features
- ✅ Non-root execution (appuser:1000)
- ✅ Multi-stage build (reduced attack surface)
- ✅ Health checks (orchestration ready)
- ✅ Read-only volumes where applicable
- ✅ No hardcoded secrets (env-based config)

---

## Common Commands

### Lifecycle Management

```bash
# Start services
docker-compose up -d

# Stop services (preserve data)
docker-compose stop

# Remove containers (keep volumes)
docker-compose down

# Remove everything (full cleanup)
docker-compose down -v

# View logs
docker-compose logs -f app
docker-compose logs -f db

# Rebuild image after code changes
docker-compose up -d --build
```

### Database Management

```bash
# Access MySQL CLI
docker-compose exec db mysql -u raportprodukcyjny -p raportprodukcyjny

# Backup database
docker-compose exec db mysqldump -u raportprodukcyjny -p raportprodukcyjny > backup.sql

# Restore database
docker-compose exec -T db mysql -u raportprodukcyjny -p raportprodukcyjny < backup.sql
```

### Application Management

```bash
# Execute Python script in container
docker-compose exec app python scripts/raporty.py

# Create admin user
docker-compose exec app python scripts/print_users.py

# View application logs
docker-compose logs app --tail=100 -f

# Access shell in container
docker-compose exec app /bin/sh
```

---

## Troubleshooting

### Service Won't Start

```bash
# Check logs
docker-compose logs app

# Verify health
docker-compose ps

# Common issues:
# - Port 8082 already in use → Change PORT in .env
# - DB connection failed → Check DB_HOST, DB_PORT, credentials
# - Permission errors → Run `docker-compose up -d` as admin/sudo if needed
```

### Database Connection Issues

```bash
# Test MySQL connection
docker-compose exec app mysql -h db -u raportprodukcyjny -p

# Check if db service is healthy
docker-compose exec db mysqladmin ping -h localhost

# Restart database
docker-compose restart db
```

### Port Conflicts

```bash
# Change port in .env
PORT=9090  # or any available port

# Rebuild and restart
docker-compose up -d --force-recreate
```

---

## Production Deployment

### Recommendations

1. **Secrets Management**
   - Use Docker secrets or external vault (Kubernetes, HashiCorp Vault)
   - Never commit `.env` with real credentials

2. **Database**
   - Use managed database service (RDS, Azure Database for MySQL)
   - Configure automated backups
   - Enable SSL/TLS for connections

3. **Logging**
   - Aggregate logs to ELK, Splunk, or cloud logging service
   - Use Docker logging drivers

4. **Orchestration**
   - Use Kubernetes or Docker Swarm for multi-instance deployment
   - Configure proper resource limits and requests

5. **Monitoring**
   - Health checks already configured
   - Add metrics collection (Prometheus, New Relic)
   - Alert on failure conditions

### Scale Horizontally

```yaml
# Multi-instance setup (requires reverse proxy like nginx)
services:
  app1:
    # ... same as app
    container_name: raportprodukcyjny_app1
  
  app2:
    # ... same as app
    container_name: raportprodukcyjny_app2
  
  app3:
    # ... same as app  
    container_name: raportprodukcyjny_app3
```

---

## Network Connectivity

### Internal Network: `raportprodukcyjny_net` (bridge)

- **app** → **db**
  - Hostname: `db`
  - Port: 3306 (internal)

- **External Access**
  - Port 8082 exposed to host
  - Configure firewall/load balancer for production

---

## Health Checks

### App Service Check
```bash
# HTTP endpoint check
curl http://localhost:8082/

# Check via docker
docker-compose ps  # Shows health status
```

### Database Service Check  
```bash
# MySQL ping
docker-compose exec db mysqladmin ping -h localhost

# Via docker
docker-compose ps  # Shows health status
```

---

## Performance Tuning

### Environment Variables
```env
# In .env
WORKERS=4          # Worker processes (adjust to CPU cores)
HOST=0.0.0.0      # Bind to all interfaces
PORT=8082         # Application port
```

### Docker Resources
```yaml
# In docker-compose.yml (optional)
services:
  app:
    mem_limit: 512m
    cpus: 1.0
  db:
    mem_limit: 1g
    cpus: 2.0
```

---

## Backup & Restore

### Full Backup
```bash
# Backup database
docker-compose exec db mysqldump -u raportprodukcyjny -p raportprodukcyjny > db_backup.sql

# Backup volumes
docker run --rm -v raportprodukcyjny_db_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/db_volume_backup.tar.gz -C /data .
```

### Full Restore
```bash
# Restore database
docker-compose exec -T db mysql -u raportprodukcyjny -p raportprodukcyjny < db_backup.sql

# Restore volumes
docker run --rm -v raportprodukcyjny_db_data:/data -v $(pwd):/backup \
  alpine tar xzf /backup/db_volume_backup.tar.gz -C /data
```

---

## Additional Resources

- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Python:3.11-slim Image](https://hub.docker.com/_/python)
- [MySQL 8.0 Image](https://hub.docker.com/_/mysql)
- [Flask Deployment Guide](https://flask.palletsprojects.com/deployment/)
