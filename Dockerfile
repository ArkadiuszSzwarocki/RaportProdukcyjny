FROM python:3.11-slim as builder
WORKDIR /tmp
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.11-slim
WORKDIR /app
RUN useradd -m -u 1000 appuser

# Copy Python dependencies from builder
COPY --from=builder /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH

# Copy application
COPY --chown=appuser:appuser . .

# Timezone
ENV TZ=Europe/Warsaw
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8082', timeout=5)" || exit 1

EXPOSE 8082
# UTWÓRZ KATALOG I NADAJ UPRAWNIENIA (TO SĄ KLUCZOWE LINIE)
RUN mkdir -p /app/raporty /app/logs && \
    chown -R appuser:appgroup /app && \
    chmod -R 755 /app

USER appuser

CMD ["python", "app.py"]