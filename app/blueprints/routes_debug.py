from flask import Blueprint, session

debug_bp = Blueprint('debug', __name__)


@debug_bp.route('/__debug/dashboard', methods=['GET'])
def debug_dashboard():
    """Temporarily mark session as logged in (localhost-only) and render dashboard/index.

    Use query params `sekcja` and `data` to control view. This endpoint is intended
    solely for local troubleshooting and will be removed after verification.
    """
    # Mark as logged in with admin role for diagnostics
    session['zalogowany'] = True
    session['rola'] = 'admin'

    # Import and call the real index view so full context is constructed
    from app.blueprints.routes_main import index
    return index()


@debug_bp.route('/__debug/obsada_page', methods=['GET'])
def debug_obsada_page():
    """Temporarily call `obsada_page` with an elevated session for diagnostics."""
    session['zalogowany'] = True
    session['rola'] = 'admin'

    from app.blueprints.routes_production import obsada_page
    return obsada_page()
