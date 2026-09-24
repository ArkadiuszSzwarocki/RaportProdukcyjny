"""
Version: 1.2.0
Description: Main entrypoint for RaportProdukcyjny application.
Supports WSGI servers (Waitress/Gunicorn) in production without debugger,
and Flask dev server only when debug mode is explicitly requested.
"""

import os
import sys
from app.core.factory import create_app

# Create and configure Flask application instance
app = create_app()


def run_development_server(application, host: str, port: int, ssl_context) -> None:
    """Run Flask built-in development server with debugger and reloader."""
    print("[WARNING] Running development server with debugger. Do NOT use in production!")
    print(f"[OK] Auto-reload and interactive debugger enabled on {host}:{port}")
    application.run(
        host=host,
        port=port,
        debug=True,
        use_reloader=True,
        use_debugger=True,
        threaded=True,
        ssl_context=ssl_context
    )


def run_production_server(application, host: str, port: int, ssl_context) -> None:
    """Run production WSGI server (Gunicorn on Linux or Waitress)."""
    server_choice = os.environ.get('WSGI_SERVER', '').lower()

    # Attempt to run Gunicorn if specified or on Unix/Linux
    if server_choice == 'gunicorn' or (server_choice == '' and sys.platform != 'win32'):
        try:
            from gunicorn.app.base import BaseApplication

            class StandaloneGunicornApp(BaseApplication):
                def __init__(self, app_instance, options=None):
                    self.options = options or {}
                    self.application = app_instance
                    super().__init__()

                def load_config(self):
                    for key, value in self.options.items():
                        if key in self.cfg.settings and value is not None:
                            self.cfg.set(key.lower(), value)

                def load(self):
                    return self.application

            options = {
                'bind': f'{host}:{port}',
                'workers': int(os.environ.get('GUNICORN_WORKERS', '2')),
                'threads': int(os.environ.get('GUNICORN_THREADS', '4')),
                'timeout': int(os.environ.get('GUNICORN_TIMEOUT', '120')),
                'keepalive': int(os.environ.get('GUNICORN_KEEPALIVE', '5')),
                'accesslog': '-',
                'errorlog': '-',
                'loglevel': os.environ.get('LOG_LEVEL', 'info').lower(),
            }
            if ssl_context and isinstance(ssl_context, tuple):
                options['certfile'] = ssl_context[0]
                options['keyfile'] = ssl_context[1]

            print(f"[OK] Starting production WSGI server (Gunicorn) on {host}:{port}")
            StandaloneGunicornApp(application, options).run()
            return
        except ImportError:
            pass

    # Default production WSGI server: Waitress
    from waitress import serve
    threads = int(os.environ.get('WAITRESS_THREADS', '8'))
    timeout = int(os.environ.get('WAITRESS_TIMEOUT', '120'))
    print(f"[OK] Starting production WSGI server (Waitress) on {host}:{port} with {threads} threads")
    serve(
        application,
        host=host,
        port=port,
        threads=threads,
        channel_timeout=timeout,
        ident="RaportProdukcyjny"
    )


if __name__ == '__main__':
    pid = os.getpid()
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', '8082'))

    # SSL configuration
    cert_path = os.path.join('certs', 'cert.pem')
    key_path = os.path.join('certs', 'key.pem')
    ssl_context = None
    protocol = "http"

    use_ssl = os.environ.get('USE_SSL', 'false').lower() == 'true'

    if use_ssl and os.path.exists(cert_path) and os.path.exists(key_path):
        ssl_context = (cert_path, key_path)
        protocol = "https"
        app.config['PREFERRED_URL_SCHEME'] = 'https'
    else:
        app.config['PREFERRED_URL_SCHEME'] = 'http'

    # Environment & debug detection
    flask_env = os.environ.get('FLASK_ENV', 'production').lower()
    debug_mode = (
        os.environ.get('FLASK_DEBUG', '0').lower() in ('1', 'true', 'yes') or
        os.environ.get('DEBUG', 'false').lower() == 'true' or
        flask_env == 'development'
    )

    print(f"\n{'='*70}")
    print(f"[OK] RaportProdukcyjny Server (pid={pid})")
    print(f"[OK] Environment: {flask_env.upper()} (debug={debug_mode})")
    print(f"[OK] Protocol: {protocol.upper()}")
    print(f"[OK] Address: {protocol}://{host}:{port}")
    if protocol == "https":
        print(f"[SSL] Certificates loaded ({cert_path}).")
    else:
        if os.path.exists(cert_path):
            print(f"[INFO] Certificates found, but SSL disabled (USE_SSL=false).")
        print(f"[INFO] Server running in HTTP mode.")
    print(f"{'='*70}\n")

    if debug_mode:
        run_development_server(app, host, port, ssl_context)
    else:
        run_production_server(app, host, port, ssl_context)
