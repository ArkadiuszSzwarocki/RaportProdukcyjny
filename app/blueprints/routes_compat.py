"""Backward compatibility and utility routes for legacy support."""

from flask import Blueprint, redirect, url_for, send_from_directory, jsonify, current_app
from app.decorators import login_required
from app.blueprints.routes_planning import dodaj_plan_zaawansowany, dodaj_plan, usun_plan
import os
from datetime import datetime

compat_bp = Blueprint('compat', __name__)


# --- Health Check Endpoint ---

@compat_bp.route('/health', methods=['GET'])
@compat_bp.route('/.health', methods=['GET'])
def health_check():
    """
    Health check endpoint for container orchestration (Docker, Kubernetes).
    Returns JSON status for load balancers and orchestration platforms.
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

    health_data = {
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
def alias_dodaj_plan_zaawansowany():
    """Legacy route - forwards to routes_api.dodaj_plan_zaawansowany()"""
    return dodaj_plan_zaawansowany()


@compat_bp.route('/dodaj_plan', methods=['POST'])
@login_required
def alias_dodaj_plan():
    """Legacy route - forwards to routes_api.dodaj_plan()"""
    return dodaj_plan()


@compat_bp.route('/usun_plan/<int:id>', methods=['POST'])
@login_required
def alias_usun_plan(id):
    """Legacy route - forwards to routes_api.usun_plan()"""
    return usun_plan(id)


# --- Favicon and well-known routes ---

@compat_bp.route('/favicon.ico')
def favicon():
    """Serve favicon at root to avoid 404s from browsers."""
    try:
        from flask import current_app
        static_folder = current_app.static_folder or os.path.join(current_app.root_path, 'static')
        # Try common favicon files in order. Fall back to the bundled PNG logo.
        for fname in ('favicon.ico', 'favicon.svg', 'agro_logo.png'):
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
def _well_known_devtools():
    """Respond to Chrome devtools well-known requests."""
    return ('', 204)


@compat_bp.route('/.well-known/<path:subpath>')
def _well_known_generic(subpath):
    """Generic handler for any /.well-known probes to reduce noisy 404s."""
    return ('', 204)
