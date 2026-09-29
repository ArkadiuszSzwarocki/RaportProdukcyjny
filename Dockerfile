FROM python:3.11-slim AS builder
WORKDIR /tmp
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.11-slim
WORKDIR /app
RUN groupadd -r appgroup || true && useradd -m -u 1000 -g appgroup appuser

RUN apt-get update && apt-get install -y --no-install-recommends \
    default-mysql-client \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH
COPY --chown=appuser:appuser . .

ENV TZ=Europe/Warsaw
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# TLS is expected to terminate at the ingress/reverse proxy.  The container
# healthcheck talks only to its own loopback HTTP listener and needs no TLS bypass.
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python -c "import requests; r=requests.get('http://127.0.0.1:8082/', timeout=5); r.raise_for_status()" || exit 1

EXPOSE 8082
RUN mkdir -p /app/raporty /app/logs /app/certs && \
    cp -r /app/config /app/config_fallback && \
    chown -R appuser:appgroup /app && \
    chmod 750 /app && \
    chmod 700 /app/certs && \
    chmod 750 /app/raporty /app/logs

USER appuser
CMD ["gunicorn", "-c", "gunicorn.conf.py", "wsgi:app"]
