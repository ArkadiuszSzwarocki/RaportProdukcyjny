from flask import Blueprint

traceability_bp = Blueprint('traceability', __name__, template_folder='templates')

from . import routes
