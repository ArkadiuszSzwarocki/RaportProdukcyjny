from flask import Blueprint
from app.decorators import login_required_response

agro_warehouse_bp = Blueprint('agro_warehouse', __name__)


@agro_warehouse_bp.before_request
def authorize_legacy_warehouse():
    denied = login_required_response()
    if denied is not None:
        return denied
    from app.core.logistics_permissions import enforce_logistics_permissions
    return enforce_logistics_permissions(default_line='AGRO')
