from flask import Blueprint, jsonify, request, session
from app.services.scanner_sync_service import ScannerSyncService
from app.decorators import login_required

def register_api_scanner_sync_routes(bp: Blueprint):
    """Register endpoints for offline scanner batch synchronization."""

    @bp.route('/api/scanner/sync-batch', methods=['POST'])
    @login_required
    def sync_offline_scans():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({'success': False, 'message': 'Wymagany obiekt JSON.'}), 400
        owner = str(payload.get('owner_user_id') or '').strip()
        active_owner = str(session.get('user_id') or '').strip()
        if not owner.isdigit() or owner != active_owner:
            return jsonify({'success': False, 'error': 'offline_owner_mismatch'}), 403
        events = payload.get('events') or []
        user_login = session.get('login')
        if not user_login:
            return jsonify({'success': False, 'error': 'unauthenticated'}), 401

        if not isinstance(events, list) or len(events) == 0:
            return jsonify({'success': False, 'message': 'Brak zdarzeń do synchronizacji.'}), 400
        if len(events) > 500 or any(not isinstance(event, dict) for event in events):
            return jsonify({'success': False, 'message': 'Nieprawidłowa lista zdarzeń.'}), 400

        result = ScannerSyncService.process_sync_batch(events=events, user_login=user_login)
        return jsonify({
            'success': True,
            'data': result
        })
