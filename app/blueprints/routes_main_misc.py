import json
from typing import Tuple

from flask import current_app, jsonify, redirect, request, session, url_for, flash


def register_main_misc_routes(main_bp):
    @main_bp.route('/set_hall_view/<hall>')
    def set_hall_view_path(hall):
        """Pin the current view to a specific hall for users with multi-hall access."""
        if hall in ['PSD', 'AGRO']:
            session['selected_hall_view'] = hall
            flash(f'Widok przełączony na: {"Hala 1 (PSD)" if hall == "PSD" else "Hala 2 (Agro)"}', 'info')
        elif hall == 'ALL':
            session.pop('selected_hall_view', None)
            flash('Widok przełączony na: Wszystkie hale', 'info')

        sekcja = request.args.get('sekcja')
        data_value = request.args.get('data')
        return redirect(url_for('main.index', linia=hall, sekcja=sekcja, data=data_value))

    @main_bp.route('/favicon.ico')
    @main_bp.route('/apple-touch-icon.png')
    @main_bp.route('/apple-touch-icon-precomposed.png')
    def favicon():
        """Silence favicon/apple-touch-icon 404 noise in logs."""
        return ('', 204)

    @main_bp.route('/debug/modal-move', methods=['POST'])
    def debug_modal_move() -> Tuple[str, int]:
        """Log modal-move debug data from client (AJAX)."""
        try:
            data = request.get_json(force=True)
            try:
                current_app.logger.info('Modal-move debug: %s', json.dumps(data, ensure_ascii=False))
            except Exception:
                current_app.logger.info('Modal-move debug: %s', str(data))
        except Exception as error:
            try:
                current_app.logger.exception('Failed to record modal-move debug: %s', error)
            except Exception:
                pass
        return ('', 204)

    @main_bp.route('/debug/whoami')
    def debug_whoami():
        """Temporary debug endpoint: returns session role and session keys for localhost only."""
        ip = request.remote_addr
        if ip not in ('127.0.0.1', '::1', 'localhost'):
            return 'Forbidden', 403

        return jsonify(
            {
                'remote_addr': ip,
                'session_role': session.get('rola'),
                'session_keys': list(session.keys()),
            }
        )