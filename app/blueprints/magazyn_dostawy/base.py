from flask import Blueprint, request, session, jsonify
from app.decorators import login_required_response

magazyn_dostawy_bp = Blueprint('magazyn_dostawy', __name__, url_prefix='/magazyn-dostawy')


@magazyn_dostawy_bp.before_request
def require_delivery_warehouse_login():
    denied = login_required_response()
    if denied is not None:
        return denied
    if not session.get('zalogowany'):
        if request.method in {'GET', 'HEAD'}:
            return None
        return jsonify(success=False, error='unauthenticated'), 401
    from app.core.logistics_permissions import enforce_logistics_permissions
    return enforce_logistics_permissions()

# Importujemy trasy po utworzeniu obiektu blueprint, aby uniknąć problemu z importem cyklicznym.
# Trasy zostaną zarejestrowane na magazyn_dostawy_bp.
from .routes import *
