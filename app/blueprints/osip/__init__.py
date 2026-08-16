"""
Blueprint dla modułu Magazynu Zewnętrznego OSIP.
"""
from flask import Blueprint

osip_bp = Blueprint('osip', __name__, url_prefix='/osip')

from app.blueprints.osip import routes  # noqa
