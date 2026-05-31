"""Planning and management routes (formerly in routes_api.py ZARZĄDZANIE section)."""

from flask import Blueprint, request, session, url_for
from datetime import date
from .adjustments import register_planning_adjustment_routes
from .creation import register_planning_creation_routes
from .lifecycle import register_planning_lifecycle_routes
from .quality import register_planning_quality_routes

planning_bp = Blueprint('planning', __name__)


def bezpieczny_powrot():
    """Return to appropriate view based on user role."""
    # Prefer returning to explicit context from current action.
    sekcja = request.args.get('sekcja') or request.form.get('sekcja')
    linia = request.args.get('linia') or request.form.get('linia')
    data_val = request.form.get('data_planu') or request.form.get('data_powrotu') or request.args.get('data')

    if request.referrer:
        try:
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(request.referrer)
            qs = parse_qs(parsed.query)
            if not data_val:
                if 'data' in qs: data_val = qs['data'][0]
                elif 'dzisiaj' in qs: data_val = qs['dzisiaj'][0]
            if not sekcja and 'sekcja' in qs:
                sekcja = qs['sekcja'][0]
            if not linia and 'linia' in qs:
                linia = qs['linia'][0]
        except Exception:
            pass

    data_val = data_val or str(date.today())
    linia = linia or session.get('selected_hall_view') or 'PSD'

    if sekcja:
        return url_for('main.index', sekcja=sekcja, data=data_val, linia=linia)

    if session.get('rola') == 'planista' or request.form.get('widok_powrotu') == 'planista':
        return url_for('planista.panel_planisty', data=data_val)

    role = session.get('rola', '')
    if role in ['lider', 'produkcja']:
        return url_for('planista.bufor_page')
    if role == 'admin':
        return url_for('admin.admin_panel')

    return url_for('main.index', sekcja='Zasyp', data=data_val, linia=linia)


# Use `log_plan_history` implementation from `app.db` to avoid duplicate logic
register_planning_adjustment_routes(planning_bp, return_url_builder=bezpieczny_powrot)
register_planning_creation_routes(planning_bp, return_url_builder=bezpieczny_powrot)
register_planning_lifecycle_routes(planning_bp, return_url_builder=bezpieczny_powrot)
register_planning_quality_routes(planning_bp, return_url_builder=bezpieczny_powrot)
