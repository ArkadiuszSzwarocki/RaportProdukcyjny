"""Healthcheck and system readiness diagnostic endpoint.
Provides health monitoring status for Docker/Kubernetes/monitoring tools.
"""

import time
import os
import psutil
from flask import jsonify
from app.core.database import get_db_connection


def register_api_health_routes(api_bp):
    """Register system health diagnostic route."""

    @api_bp.route('/health', methods=['GET'])
    def healthcheck():
        """Evaluate application components and return operational health."""
        start_time = time.time()
        db_status = "healthy"
        db_latency_ms = 0.0

        conn = None
        try:
            db_t0 = time.time()
            conn = get_db_connection(retries=1)
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            conn.close()
            db_latency_ms = round((time.time() - db_t0) * 1000, 2)
        except Exception as e:
            db_status = f"unhealthy: {str(e)}"
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

        # Memory and process stats
        memory_usage_mb = 0.0
        cpu_percent = 0.0
        try:
            proc = psutil.Process(os.getpid())
            memory_usage_mb = round(proc.memory_info().rss / (1024 * 1024), 2)
            cpu_percent = proc.cpu_percent(interval=0.05)
        except Exception:
            pass

        total_duration_ms = round((time.time() - start_time) * 1000, 2)
        is_healthy = db_status == "healthy"

        payload = {
            "status": "UP" if is_healthy else "DEGRADED",
            "timestamp": int(time.time()),
            "database": {
                "status": db_status,
                "latency_ms": db_latency_ms
            },
            "process": {
                "pid": os.getpid(),
                "memory_mb": memory_usage_mb,
                "cpu_percent": cpu_percent
            },
            "response_time_ms": total_duration_ms
        }

        return jsonify(payload), (200 if is_healthy else 503)
