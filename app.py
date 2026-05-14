"""
Wersja: 1.1.0
Opis: Główny punkt wejściowy aplikacji RaportProdukcyjny. 
Inicjalizuje aplikację Flask i uruchamia serwer (z obsługą SSL/HTTPS).
"""

import os
import sys
from app.core.factory import create_app

# Create and configure Flask application instance
app = create_app()

if __name__ == '__main__':
    pid = os.getpid()
    
    # Konfiguracja SSL
    cert_path = os.path.join('certs', 'cert.pem')
    key_path = os.path.join('certs', 'key.pem')
    ssl_context = None
    
    if os.path.exists(cert_path) and os.path.exists(key_path):
        ssl_context = (cert_path, key_path)
        protocol = "https"
    else:
        protocol = "http"

    app.logger.info('Starting server (pid=%s) host=%s port=%s protocol=%s', pid, '0.0.0.0', 8082, protocol)
    print(f"\n{'='*70}")
    print(f"[OK] Serwer w TRYBIE DEBUG: {protocol}://localhost:8082 (pid={pid})")
    print(f"[OK] Auto-reload WŁĄCZONY - zmiany w kodzie spowodują restart")
    if protocol == "https":
        print(f"[SSL] Certyfikaty załadowane z folderu /certs")
    else:
        print(f"[SSL] BRAK certyfikatów - uruchomiono w trybie nieszyfrowanym (http)")
    print(f"{'='*70}\n")
    
    # Run Flask development server with auto-reload
    app.run(
        host='0.0.0.0',
        port=8082,
        debug=True,
        use_reloader=True,
        use_debugger=True,
        threaded=True,
        ssl_context=ssl_context
    )
