import os
import sys
import py_compile
from pathlib import Path

def check_syntax():
    """Checks all Python files for syntax errors."""
    print("--- Sprawdzanie składni Pythona ---")
    root = Path(__file__).parent.parent
    errors = 0
    for path in root.rglob("*.py"):
        if ".gemini" in str(path) or "venv" in str(path) or ".git" in str(path):
            continue
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as e:
            print(f"[SYNTAX ERROR] {path}: {e}")
            errors += 1
    return errors

def check_imports():
    """Attempts to initialize the Flask app to catch NameErrors and ImportErrors."""
    print("\n--- Sprawdzanie inicjalizacji aplikacji (Importy/Nazwy) ---")
    sys.path.append(str(Path(__file__).parent.parent))
    
    # Mocking some environment variables if needed
    os.environ['FLASK_ENV'] = 'testing'
    
    try:
        from app.core.factory import create_app
        # We don't need to run it, just create it to trigger imports
        app = create_app()
        print("[OK] Aplikacja zainicjalizowana pomyślnie.")
        return 0
    except Exception as e:
        import traceback
        print(f"[CRITICAL ERROR] Nie udało się zainicjalizować aplikacji:")
        print(traceback.format_exc())
        return 1

def check_ssl():
    """Checks for SSL certificates and reports status with requested wording."""
    print("\n--- Sprawdzanie certyfikatów SSL ---")
    root = Path(__file__).parent.parent
    cert = root / 'certs' / 'cert.pem'
    key = root / 'certs' / 'key.pem'
    
    if cert.exists() and key.exists():
        print("[OK] Certyfikaty SSL są obecne - możliwe uruchomienie w trybie HTTPS.")
        return 0
    else:
        print("[OSTRZEŻENIE] [SSL] BRAK certyfikatów - uruchomiono w trybie nieszyfrowanym (http)")
        return 0 # Still 0 because it's a valid mode, but the wording matches user request

def check_error_logs():
    """Checks recent lines of error.log and prints warnings/errors if present."""
    print("\n--- Sprawdzanie logów błędów ---")
    root = Path(__file__).parent.parent
    error_log = root / 'logs' / 'error.log'
    
    if not error_log.exists():
        print("[OK] Brak pliku logs/error.log (brak błędów).")
        return 0
        
    try:
        with open(error_log, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        recent_lines = lines[-20:] if len(lines) > 20 else lines
        errors_found = [line.strip() for line in recent_lines if 'ERROR' in line or 'CRITICAL' in line or 'Exception' in line]
        
        if errors_found:
            print(f"[OSTRZEŻENIE] Znaleziono niedawne błędy w logs/error.log (ostatnie 20 linii):")
            for err in errors_found[-5:]:
                print(f"  -> {err}")
        else:
            print("[OK] Brak niedawnych błędów/wyjątków w logs/error.log.")
    except Exception as e:
        print(f"[BŁĄD] Nie można odczytać pliku logs/error.log: {e}")
    return 0

if __name__ == "__main__":
    syntax_err = check_syntax()
    import_err = check_imports()
    check_ssl()
    check_error_logs()
    
    total = syntax_err + import_err
    if total > 0:
        print(f"\n[FAILED] Znaleziono {total} błędów.")
        sys.exit(1)
    else:
        print("\n[SUCCESS] Wszystkie testy integralności przeszły pomyślnie.")
        sys.exit(0)
