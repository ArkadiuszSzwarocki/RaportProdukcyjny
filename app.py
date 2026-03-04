"""RaportProdukcyjny: Production Management System.

Main entry point for Flask application. Creates and initializes the app,
then runs the development or production server.
"""

import os
import sys
from app.core.factory import create_app

# Create and configure Flask application instance
app = create_app()


if __name__ == '__main__':
    pid = os.getpid()
    app.logger.info('Starting server (pid=%s) host=%s port=%s', pid, '0.0.0.0', 8082)
    print(f"\n{'='*70}")
    print(f"[OK] Serwer w TRYBIE DEBUG: http://localhost:8082 (pid={pid})")
    print(f"[OK] Auto-reload WŁĄCZONY - zmiany w kodzie spowodują restart")
    print(f"{'='*70}\n")
    
    # Run Flask development server with auto-reload
    app.run(
        host='0.0.0.0',
        port=8082,
        debug=True,
        use_reloader=True,
        use_debugger=True,
        threaded=True
    )
