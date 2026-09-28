from flask import Blueprint
from app.decorators import login_required_response

magazyn_dostawy_bp = Blueprint('magazyn_dostawy', __name__, url_prefix='/magazyn-dostawy')


@magazyn_dostawy_bp.before_request
def require_delivery_warehouse_login():
    return login_required_response()

# Importujemy trasy po utworzeniu obiektu blueprint, aby uniknąć problemu z importem cyklicznym.
# Trasy zostaną zarejestrowane na magazyn_dostawy_bp.
from .routes import *
