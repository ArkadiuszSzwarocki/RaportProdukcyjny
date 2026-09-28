"""
Wersja: 1.1.0
Opis: Pakiet główny aplikacji Raport Produkcyjny.
"""

_app = None


def __getattr__(name: str):
    """Lazy-load application object when accessed via package (e.g. gunicorn app:app)."""
    global _app
    if name in ('app', 'application'):
        if _app is None:
            from app.core.factory import create_app
            _app = create_app()
        return _app
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

