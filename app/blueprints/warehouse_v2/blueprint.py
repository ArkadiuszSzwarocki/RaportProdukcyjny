from flask import Blueprint
from app.decorators import login_required_response

warehouse_v2_bp = Blueprint('warehouse_v2', __name__, url_prefix='/warehouse-v2')


@warehouse_v2_bp.before_request
def require_warehouse_v2_login():
    return login_required_response()
