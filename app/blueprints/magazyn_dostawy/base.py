from flask import Blueprint

magazyn_dostawy_bp = Blueprint('magazyn_dostawy', __name__, url_prefix='/magazyn-dostawy')

# Importujemy trasy po utworzeniu obiektu blueprint, aby uniknąć problemu z importem cyklicznym.
# Trasy zostaną zarejestrowane na magazyn_dostawy_bp.
from .routes import *
