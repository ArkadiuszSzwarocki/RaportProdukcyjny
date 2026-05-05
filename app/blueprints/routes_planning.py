"""Planning and management routes (formerly in routes_api.py ZARZĄDZANIE section)."""

from flask import Blueprint, request, session, url_for
from datetime import date
from app.blueprints.routes_planning_adjustments import register_planning_adjustment_routes
from app.blueprints.routes_planning_creation import register_planning_creation_routes
from app.blueprints.routes_planning_lifecycle import register_planning_lifecycle_routes
from app.blueprints.routes_planning_quality import register_planning_quality_routes

planning_bp = Blueprint('planning', __name__)


def bezpieczny_powrot():
    """Return to appropriate view based on user role."""
    # Prefer returning to explicit context from current action.
    sekcja = request.args.get('sekcja') or request.form.get('sekcja')
    linia = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
    data = request.form.get('data_planu') or request.form.get('data_powrotu') or request.args.get('data') or str(date.today())

    if sekcja:
        return url_for('main.index', sekcja=sekcja, data=data, linia=linia)

    if session.get('rola') == 'planista' or request.form.get('widok_powrotu') == 'planista':
        return url_for('planista.panel_planisty', data=data)

    role = session.get('rola', '')
    if role in ['lider', 'produkcja']:
        return url_for('planista.bufor_page')
    if role == 'admin':
        return url_for('admin.admin_panel')

    return url_for('main.index', sekcja='Zasyp', data=data, linia=linia)


# Use `log_plan_history` implementation from `app.db` to avoid duplicate logic
register_planning_adjustment_routes(planning_bp, return_url_builder=bezpieczny_powrot)
register_planning_creation_routes(planning_bp, return_url_builder=bezpieczny_powrot)
register_planning_lifecycle_routes(planning_bp, return_url_builder=bezpieczny_powrot)
register_planning_quality_routes(planning_bp, return_url_builder=bezpieczny_powrot)



