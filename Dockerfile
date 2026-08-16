FROM python:3.11-slim as builder
WORKDIR /tmp
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.11-slim
WORKDIR /app
RUN groupadd -r appgroup || true && useradd -m -u 1000 -g appgroup appuser

# Install mysqldump for database backups
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-mysql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy Python dependencies from builder
COPY --from=builder /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH

# Copy application
COPY --chown=appuser:appuser . .

# Timezone
ENV TZ=Europe/Warsaw
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Health check (handles both http and https)
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python -c "import requests; \
    try: requests.get('https://localhost:8082', timeout=5, verify=False); \
    except: requests.get('http://localhost:8082', timeout=5)" || exit 1

EXPOSE 8082
# UTWÓRZ KATALOGI I NADAJ UPRAWNIENIA
RUN mkdir -p /app/raporty /app/logs /app/certs && \
    chown -R appuser:appgroup /app && \
    chmod -R 755 /app

USER appuser

CMD ["python", "app.py"]