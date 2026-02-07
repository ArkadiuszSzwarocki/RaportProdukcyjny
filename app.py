"""RaportProdukcyjny: Production Management System.

Main entry point for Flask application. Creates and initializes the app,
then runs the development or production server.
"""

from waitress import serve
from app.core.factory import create_app

# Create and configure Flask application instance
app = create_app()


if __name__ == '__main__':
    # Log startup information including PID and port to help detect multiple instances
    try:
        import os as _os
        pid = _os.getpid()
    except Exception:
        pid = 'unknown'
    try:
        app.logger.info('Starting server (pid=%s) host=%s port=%s', pid, '0.0.0.0', 8082)
    except Exception:
        pass
    print("[OK] Serwer wystartował: http://YOUR_IP_ADDRESS:8082 (pid=%s)" % pid)
    serve(app, host='0.0.0.0', port=8082, threads=6)
