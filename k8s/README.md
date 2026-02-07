# Kubernetes Deployment Guide

## Overview

This directory contains Kubernetes manifests for deploying RaportProdukcyjny in production environments. The setup includes:

- Namespace isolation
- MySQL database with persistent storage
- Flask application with auto-scaling
- Service mesh networking
- RBAC security

## Prerequisites

- Kubernetes cluster (v1.24+)
- `kubectl` CLI configured
- Persistent Volume provisioner (e.g., Longhorn, AWS EBS)
- Ingress Controller (nginx recommended)
- Cert-manager (for TLS certificates)

## Quick Start

### 1. Prepare Environment

```bash
# Update image registry and domain name
# Edit k8s/*.yaml files:
# - Change ghcr.io/arkadiuszszwarocki/raportprodukcyjny:latest to your registry
# - Change raportprodukcyjny.example.com to your domain
```

### 2. Deploy to Kubernetes

```bash
# Set kubectl context
kubectl config use-context <your-cluster>

# Apply manifests in order
kubectl apply -f k8s/00-namespace-config.yaml
kubectl apply -f k8s/01-mysql.yaml
kubectl apply -f k8s/02-app.yaml
kubectl apply -f k8s/03-ingress.yaml

# Verify deployment
kubectl get all -n raportprodukcyjny
kubectl get pvc -n raportprodukcyjny
```

### 3. Update Secrets

```bash
# Edit and apply secrets (IMPORTANT!)
kubectl edit secret app-secrets -n raportprodukcyjny

# Set required values:
# - SECRET_KEY: Random 32+ character string
# - DB_PASSWORD: Strong password
# - INITIAL_ADMIN_PASSWORD: Admin password
```

### 4. Monitor Deployment

```bash
# Check pod status
kubectl get pods -n raportprodukcyjny -w

# View logs
kubectl logs -n raportprodukcyjny -l app=raportprodukcyjny -f

# Get service endpoints
kubectl get svc -n raportprodukcyjny
```

---

## File Descriptions

### 00-namespace-config.yaml
- **Namespace:** `raportprodukcyjny` - Isolated namespace for the application
- **ConfigMap:** Application configuration (environment variables)
- **Secret:** Sensitive data (passwords, API keys)
- **PVCs:** Persistent volumes for MySQL, logs, and reports

### 01-mysql.yaml
- **Deployment:** MySQL 8.0 database server
- **Service:** Internal database service (ClusterIP)
- **Health Checks:** Liveness and readiness probes
- **Resource Limits:** Memory and CPU constraints
- **Persistent Storage:** Database files on shared volume

### 02-app.yaml
- **Deployment:** Flask application (2 replicas by default)
- **Service:** LoadBalancer service for external access
- **HPA:** Horizontal Pod Autoscaler (2-5 replicas based on CPU/memory)
- **RBAC:** Service account and role bindings
- **Security:** SecurityContext for restricted permissions

### 03-ingress.yaml
- **Ingress:** HTTP/HTTPS routing
- **TLS:** Automatic certificate management via cert-manager
- **NetworkPolicy:** Pod-to-pod communication rules
- **Rate Limiting:** Ingress rate limiting enabled

---

## Configuration

### Environment Variables

Edit `00-namespace-config.yaml` to adjust:

```yaml
data:
  FLASK_ENV: "production"
  TZ: "Europe/Warsaw"
  DB_HOST: "mysql-service"
  PORT: "8082"
```

### Secrets

```bash
# Generate strong secrets
openssl rand -base64 32  # For SECRET_KEY

# Edit secrets
kubectl edit secret app-secrets -n raportprodukcyjny
```

### Resource Limits

Adjust in `02-app.yaml` and `01-mysql.yaml`:

```yaml
resources:
  requests:
    memory: "256Mi"
    cpu: "250m"
  limits:
    memory: "512Mi"
    cpu: "500m"
```

### Auto-scaling

Configure in `02-app.yaml`:

```yaml
minReplicas: 2
maxReplicas: 5
metrics:
  - cpu: 70%
  - memory: 80%
```

---

## Common Commands

### Deployment Management

```bash
# View deployment status
kubectl get deployment -n raportprodukcyjny

# Scale deployment
kubectl scale deployment app -n raportprodukcyjny --replicas=3

# Restart deployment
kubectl rollout restart deployment/app -n raportprodukcyjny

# View rollout history
kubectl rollout history deployment/app -n raportprodukcyjny

# Rollback to previous version
kubectl rollout undo deployment/app -n raportprodukcyjny
```

### Pod Management

```bash
# View pod logs
kubectl logs -n raportprodukcyjny <pod-name>

# Follow logs in real-time
kubectl logs -n raportprodukcyjny <pod-name> -f

# Execute command in pod
kubectl exec -n raportprodukcyjny <pod-name> -- python scripts/raporty.py

# Get interactive shell
kubectl exec -it -n raportprodukcyjny <pod-name> -- /bin/sh
```

### Debug and Troubleshooting

```bash
# Describe pod for events
kubectl describe pod -n raportprodukcyjny <pod-name>

# Watch pod status
kubectl get pods -n raportprodukcyjny -w

# Check service endpoints
kubectl get endpoints -n raportprodukcyjny

# View resource usage
kubectl top nodes
kubectl top pod -n raportprodukcyjny
```

### Database Management

```bash
# Connect to MySQL
kubectl exec -it -n raportprodukcyjny <mysql-pod> -- mysql -u raportprodukcyjny -p

# Backup database
kubectl exec -n raportprodukcyjny <mysql-pod> -- mysqldump \
  -u raportprodukcyjny -p raportprodukcyjny > backup.sql

# Restore database
kubectl exec -i -n raportprodukcyjny <mysql-pod> -- mysql \
  -u raportprodukcyjny -p raportprodukcyjny < backup.sql
```

### Persistent Volumes

```bash
# View PVCs
kubectl get pvc -n raportprodukcyjny

# View PVs
kubectl get pv

# Check storage usage
kubectl exec -n raportprodukcyjny <pod-name> -- df -h
```

---

## Monitoring & Observability

### Health Checks

- **Liveness Probe:** Restarts unhealthy pods
- **Readiness Probe:** Removes unhealthy pods from load balancer
- **Startup Probe:** Allows app time to initialize

### Viewing Metrics

```bash
# If Prometheus is installed
kubectl port-forward -n monitoring svc/prometheus 9090:9090

# View metrics in browser: http://localhost:9090
```

### Logs Aggregation

```bash
# Stream all namespace logs
kubectl logs -n raportprodukcyjny -f --all-containers=true

# Export logs for external system
kubectl logs -n raportprodukcyjny deployment/app > logs.txt
```

---

## Security Best Practices

### Applied in this Setup
- ✅ Non-root user execution (UID 1000)
- ✅ Read-only filesystem where possible
- ✅ Network policies (NSP) for traffic control
- ✅ RBAC with minimal service account permissions
- ✅ Secrets not in ConfigMap
- ✅ Health checks for high availability

### Additional Recommendations
- Implement Pod Security Policy (PSP) or Pod Security Standards (PSS)
- Use node affinity for pod schedule control
- Enable audit logging on Kubernetes API
- Implement network policies for all pods
- Use container image scanning in CI/CD pipeline
- Regularly update Kubernetes components and container images

---

## Troubleshooting

### Pods Not Starting

```bash
# Check events
kubectl describe pod -n raportprodukcyjny <pod-name>

# Common causes:
# - ImagePullBackOff: Check registry credentials
# - CrashLoopBackOff: Check application logs
# - Pending: Check PVC or resource availability
```

### Database Connection Issues

```bash
# Test connectivity from app pod
kubectl exec -it -n raportprodukcyjny <app-pod> -- \
  nc -zv mysql-service 3306

# Check service DNS
kubectl exec -it -n raportprodukcyjny <app-pod> -- \
  nslookup mysql-service
```

### Persistent Volume Issues

```bash
# Check PVC status
kubectl describe pvc -n raportprodukcyjny

# Check PV status
kubectl describe pv

# Common causes:
# - PVC pending: Storage provisioner not available
# - PVC bound to wrong PV: Delete and recreate
```

### High Memory/CPU Usage

```bash
# Check resource metrics
kubectl top pod -n raportprodukcyjny

# Increase limits
kubectl set resources deployment app \
  -n raportprodukcyjny \
  --limits=cpu=1000m,memory=1Gi \
  --requests=cpu=500m,memory=512Mi
```

---

## Production Checklist

- [ ] Registry credentials configured
- [ ] Secrets updated with production values
- [ ] Domain name updated in Ingress
- [ ] SSL certificate issued and installed
- [ ] Database backup strategy in place
- [ ] Monitoring and alerting configured
- [ ] Resource limits appropriate for workload
- [ ] Network policies reviewed
- [ ] RBAC permissions verified
- [ ] Disaster recovery plan documented
- [ ] Load testing completed
- [ ] Staging environment verified

---

## Advanced Features

### Blue-Green Deployment

```bash
# Deploy new version alongside old
kubectl apply -f k8s/02-app-blue.yaml
# Update service selector to point to green version
```

### Canary Deployment

```bash
# Use Flagger or Istio for gradual rollout
# Or manually adjust replica counts
```

### Multi-Region Deployment

```bash
# Use federation or gitops tools
# Deploy same manifests to multiple clusters
```

---

## Related Documentation

- [Kubernetes Official Docs](https://kubernetes.io/docs/)
- [kubectl Cheat Sheet](https://kubernetes.io/docs/reference/kubectl/cheatsheet/)
- [Best Practices](https://kubernetes.io/docs/concepts/configuration/overview/)
- [Security Documentation](https://kubernetes.io/docs/concepts/security/)
