"""Backward compatibility and utility routes for legacy support."""

from typing import Tuple, Dict, Any, Union
from flask import Blueprint, redirect, url_for, send_from_directory, jsonify, current_app, Response
from app.decorators import login_required
import os
from datetime import datetime

compat_bp = Blueprint('compat', __name__)


def _call_view(endpoint: str, *args, **kwargs):
    return current_app.view_functions[endpoint](*args, **kwargs)


# --- Health Check Endpoint ---

@compat_bp.route('/health', methods=['GET'])
@compat_bp.route('/.health', methods=['GET'])
def health_check() -> Tuple[Response, int]:
    """
    Health check endpoint for container orchestration (Docker, Kubernetes).
    Returns JSON status for load balancers and orchestration platforms.
    
    Returns:
        Tuple[Response, int]: JSON health status with HTTP status code
    """
    try:
        from app.db import get_db_connection
        # Try to establish database connection
        conn = get_db_connection()
        if conn:
            conn.close()
            db_status = "healthy"
        else:
            db_status = "unhealthy"
    except Exception as e:
        db_status = f"error: {str(e)}"

    health_data: Dict[str, Any] = {
        "status": "ok" if db_status == "healthy" else "degraded",
        "timestamp": datetime.now().isoformat(),
        "service": "raportprodukcyjny",
        "db": db_status,
        "version": current_app.config.get("VERSION", "unknown")
    }
    
    status_code = 200 if db_status == "healthy" else 503
    return jsonify(health_data), status_code


# --- Backward-compatible aliases for forms that post to root paths ---
# These ensure legacy forms continue to work without breaking existing HTML

@compat_bp.route('/dodaj_plan_zaawansowany', methods=['POST'])
@login_required
def alias_dodaj_plan_zaawansowany() -> Union[Response, str]:
    """Legacy route - forwards to routes_api.dodaj_plan_zaawansowany()"""
    return _call_view('planning.dodaj_plan_zaawansowany')


@compat_bp.route('/dodaj_plan', methods=['POST'])
@login_required
def alias_dodaj_plan() -> Union[Response, str]:
    """Legacy route - forwards to routes_api.dodaj_plan()"""
    return _call_view('planning.dodaj_plan')


@compat_bp.route('/usun_plan/<int:id>', methods=['POST'])
@login_required
def alias_usun_plan(id: int) -> Union[Response, str]:
    """Legacy route - forwards to routes_api.usun_plan()"""
    return _call_view('planning.usun_plan', id)


@compat_bp.route('/przenies_zlecenie_ajax', methods=['POST'])
@login_required
def alias_przenies_zlecenie_ajax() -> Union[Response, str]:
    """Legacy route - forwards to /api/przenies_zlecenie_ajax."""
    return _call_view('planning.przenies_zlecenie_ajax')


@compat_bp.route('/przesun_zlecenie_ajax', methods=['POST'])
@login_required
def alias_przesun_zlecenie_ajax() -> Union[Response, str]:
    """Legacy route - forwards to /api/przesun_zlecenie_ajax."""
    return _call_view('planning.przesun_zlecenie_ajax')


# --- Favicon and well-known routes ---

@compat_bp.route('/favicon.ico')
def favicon() -> Union[Response, Tuple[str, int]]:
    """Serve favicon at root to avoid 404s from browsers.
    
    Returns:
        Union[Response, Tuple[str, int]]: File response or empty 204 response
    """
    try:
        from flask import current_app
        static_folder = current_app.static_folder or os.path.join(current_app.root_path, 'static')
        # Try common favicon files in order. Fall back to the bundled PNG logo.
        for fname in ('favicon.ico', 'favicon.ico', 'agro_logo.png'):
            path = os.path.join(static_folder, fname)
            if os.path.exists(path):
                try:
                    return send_from_directory(static_folder, fname)
                except Exception:
                    return redirect(url_for('static', filename=fname))
        return ('', 204)
    except Exception:
        return ('', 204)


# Some devtools/extensions request well-known files which we don't serve;
# respond with 204 No Content to avoid noisy 404/500 traces in logs.

@compat_bp.route('/.well-known/appspecific/com.chrome.devtools.json')
def _well_known_devtools() -> Tuple[str, int]:
    """Respond to Chrome devtools well-known requests."""
    return ('', 204)


@compat_bp.route('/.well-known/<path:subpath>')
def _well_known_generic(subpath: str) -> Tuple[str, int]:
    """Generic handler for any /.well-known probes to reduce noisy 404s."""
    return ('', 204)
