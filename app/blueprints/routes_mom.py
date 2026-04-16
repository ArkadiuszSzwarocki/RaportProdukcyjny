from flask import Blueprint, render_template, request, jsonify, session
from app.services.mom_service import MomService
from app.decorators import login_required, dynamic_role_required

mom_bp = Blueprint('mom', __name__)


@mom_bp.route('/agro/mom')
@login_required
@dynamic_role_required('agro_magazyn')
def index():
    """List all MOM documents."""
    status = request.args.get('status')
    data_od = request.args.get('data_od')
    data_do = request.args.get('data_do')
    moms = MomService.list_moms(limit=100, status=status, data_od=data_od, data_do=data_do)
    open_plans = MomService.get_open_plans()
    return render_template('mom.html', moms=moms, open_plans=open_plans,
                           filter_status=status, filter_od=data_od, filter_do=data_do)


@mom_bp.route('/agro/mom/<int:mom_id>')
@login_required
@dynamic_role_required('agro_magazyn')
def detail(mom_id):
    """Show single MOM detail with positions."""
    mom = MomService.get_mom(mom_id)
    if not mom:
        return jsonify({'error': 'MOM nie znaleziony'}), 404
    return render_template('mom_detail.html', mom=mom)


@mom_bp.route('/agro/api/mom/open', methods=['POST'])
@login_required
@dynamic_role_required('agro_magazyn')
def api_open():
    """Create MOM for a plan_agro order."""
    data = request.get_json(silent=True) or request.form
    plan_id = data.get('plan_id')
    if not plan_id:
        return jsonify({'error': 'Brak plan_id'}), 400
    try:
        mom_id = MomService.open_mom(int(plan_id))
        if mom_id is None:
            return jsonify({'error': 'Nie znaleziono zlecenia'}), 404
        return jsonify({'ok': True, 'mom_id': mom_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@mom_bp.route('/agro/api/mom/<int:mom_id>/refresh', methods=['POST'])
@login_required
@dynamic_role_required('agro_magazyn')
def api_refresh(mom_id):
    """Refresh moved quantities from warehouse moves."""
    ok = MomService.refresh(mom_id)
    if not ok:
        return jsonify({'error': 'MOM nie znaleziony'}), 404
    return jsonify({'ok': True})


@mom_bp.route('/agro/api/mom/<int:mom_id>/usage', methods=['POST'])
@login_required
@dynamic_role_required('agro_magazyn')
def api_save_usage(mom_id):
    """Save manually-entered usage for MOM positions."""
    data = request.get_json(silent=True)
    if not data or 'items' not in data:
        return jsonify({'error': 'Brak danych items'}), 400
    try:
        MomService.save_usage(mom_id, data['items'])
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@mom_bp.route('/agro/api/mom/<int:mom_id>/close', methods=['POST'])
@login_required
@dynamic_role_required('agro_magazyn')
def api_close(mom_id):
    """Close MOM — final reconciliation."""
    login = session.get('login', 'unknown')
    try:
        MomService.close_mom(mom_id, login)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@mom_bp.route('/agro/api/mom/<int:mom_id>/reopen', methods=['POST'])
@login_required
@dynamic_role_required('agro_magazyn')
def api_reopen(mom_id):
    """Reopen closed MOM (admin/lider)."""
    rola = session.get('rola', '')
    if rola not in ('admin', 'lider'):
        return jsonify({'error': 'Brak uprawnień'}), 403
    MomService.reopen_mom(mom_id)
    return jsonify({'ok': True})


@mom_bp.route('/agro/api/mom/<int:mom_id>/delete', methods=['DELETE'])
@login_required
@dynamic_role_required('agro_magazyn')
def api_delete(mom_id):
    """Delete MOM."""
    rola = session.get('rola', '')
    if rola not in ('admin', 'lider'):
        return jsonify({'error': 'Brak uprawnień'}), 403
    MomService.delete_mom(mom_id)
    return jsonify({'ok': True})
