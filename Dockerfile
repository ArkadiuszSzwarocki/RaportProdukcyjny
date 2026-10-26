# cspell:words setuptools ensurepip addgroup adduser libstdc
FROM python:3.11-alpine@sha256:d9368b3a5ac59afea7b5d4f2e2aea0941dbf9fdee9c369c5bec00b98244bc929 AS builder
WORKDIR /tmp
COPY requirements-build.lock requirements-linux.lock ./
RUN pip install --require-hashes --no-cache-dir -r requirements-build.lock && \
    pip install --user --require-hashes --no-build-isolation --no-cache-dir -r requirements-linux.lock && \
    pip check

FROM python:3.11-alpine@sha256:d9368b3a5ac59afea7b5d4f2e2aea0941dbf9fdee9c369c5bec00b98244bc929
WORKDIR /app
RUN addgroup -g 1000 appgroup && adduser -D -u 1000 -G appgroup appuser
RUN apk add --no-cache tzdata libstdc++

COPY --from=builder /root/.local /home/appuser/.local
# Installation tools and their bundled dependencies belong only in the builder.
RUN python -m pip uninstall --yes pip setuptools wheel packaging && \
    rm -rf /usr/local/lib/python3.11/ensurepip
ENV PATH=/home/appuser/.local/bin:$PATH
COPY --chown=appuser:appgroup . .

ENV TZ=Europe/Warsaw
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# TLS is expected to terminate at the ingress/reverse proxy.  The container
# healthcheck talks only to its own loopback HTTP listener and needs no TLS bypass.
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python -c "import requests; r=requests.get('http://127.0.0.1:8082/', timeout=5); r.raise_for_status()" || exit 1

EXPOSE 8082
RUN mkdir -p /app/raporty /app/logs /app/certs /app/static/uploads/bugs && \
    cp -r /app/config /app/config_fallback && \
    chown -R appuser:appgroup /app && \
    chmod 750 /app && \
    chmod 700 /app/certs && \
    chmod 750 /app/raporty /app/logs

USER appuser
CMD ["gunicorn", "-c", "gunicorn.conf.py", "wsgi:app"]
