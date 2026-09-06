from flask import Blueprint, jsonify, request, session
from app.services.scanner_sync_service import ScannerSyncService
from app.decorators import login_required

def register_api_scanner_sync_routes(bp: Blueprint):
    """Register endpoints for offline scanner batch synchronization."""

    @bp.route('/api/scanner/sync-batch', methods=['POST'])
    @login_required
    def sync_offline_scans():
        payload = request.get_json(silent=True) or {}
        events = payload.get('events') or []
        user_login = session.get('user', 'system')

        if not isinstance(events, list) or len(events) == 0:
            return jsonify({'success': False, 'message': 'Brak zdarzeń do synchronizacji.'}), 400

        result = ScannerSyncService.process_sync_batch(events=events, user_login=user_login)
        return jsonify({
            'success': True,
            'data': result
        })
