"""
Wersja: 1.1.1
Opis: Główny punkt wejściowy aplikacji RaportProdukcyjny. 
Obsługuje HTTP oraz opcjonalnie HTTPS (jeśli certyfikaty są w folderze /certs).
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
    
    # Domyślnie zakładamy HTTP
    protocol = "http"
    
    # Lokalnie chcemy HTTP (bo PWA i brak błędów certyfikatu), na QNAP chcemy HTTPS (bo port 443).
    is_local = os.environ.get('LOCAL_ENV', 'false').lower() == 'true'
    # Pobieramy flagę USE_SSL. Domyślnie false (HTTP), co jest idealne dla Nginx Proxy Manager.
    use_ssl = os.environ.get('USE_SSL', 'false').lower() == 'true'
    
    if use_ssl:
        if os.path.exists(cert_path) and os.path.exists(key_path):
            ssl_context = (cert_path, key_path)
            protocol = "https"
            app.config['PREFERRED_URL_SCHEME'] = 'https'
        else:
            try:
                ssl_context = 'adhoc'
                protocol = "https"
                app.config['PREFERRED_URL_SCHEME'] = 'https'
            except Exception:
                app.config['PREFERRED_URL_SCHEME'] = 'http'
                protocol = "http"
    else:
        app.config['PREFERRED_URL_SCHEME'] = 'http'

    print(f"\n{'='*70}")
    print(f"[OK] Serwer RaportProdukcyjny (pid={pid})")
    print(f"[OK] Tryb: {protocol.upper()}")
    print(f"[OK] Adres: {protocol}://localhost:8082")
    
    if protocol == "https":
        print(f"[SSL] Certyfikaty załadowane. Pamiętaj o zaakceptowaniu ryzyka w przeglądarce.")
    else:
        if os.path.exists(cert_path):
            print(f"[INFO] Certyfikaty są obecne, ale wyłączone (USE_SSL=false).")
        print(f"[INFO] Serwer działa w trybie nieszyfrowanym (HTTP).")
        
    print(f"[OK] Auto-reload WŁĄCZONY")
    print(f"[TIP] Jeśli w logach pojawi się 'Bad request version', zmień https:// na http:// w przeglądarce.")
    print(f"{'='*70}\n")
    
    # Run Flask development server with auto-reload enabled
    app.run(
        host='0.0.0.0',
        port=8082,
        debug=True,
        use_reloader=True,
        use_debugger=True,
        threaded=True,
        ssl_context=ssl_context
    )
