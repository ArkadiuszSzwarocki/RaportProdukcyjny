"""RaportProdukcyjny: Production Management System.

Main entry point for Flask application. Creates and initializes the app,
then runs the development or production server.
"""

import os
from waitress import serve
from app.core.factory import create_app

# Create and configure Flask application instance
app = create_app()


if __name__ == '__main__':
    pid = os.getpid()
    app.logger.info('Starting server (pid=%s) host=%s port=%s', pid, '0.0.0.0', 8082)
    print(f"[OK] Serwer wystartował: http://YOUR_IP_ADDRESS:8082 (pid={pid})")
    serve(app, host='0.0.0.0', port=8082, threads=6)
