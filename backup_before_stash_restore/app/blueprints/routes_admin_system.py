from flask import jsonify, redirect, render_template, request, url_for

from app.decorators import admin_required, dynamic_role_required


def register_admin_system_routes(admin_bp, *, list_online_users):
    @admin_bp.route('/admin')
    @admin_required
    def admin_panel():
        """Redirect legacy admin panel to the new modern settings dashboard."""
        return redirect(url_for('admin.admin_ustawienia'))

    @admin_bp.route('/admin/users')
    @admin_required
    def admin_users():
        """Redirect legacy users management to the new modern settings dashboard."""
        return redirect(url_for('admin.admin_ustawienia_uzytkownicy'))

    @admin_bp.route('/admin/centrum')
    @dynamic_role_required('ustawienia')
    def admin_centrum_systemowe():
        return render_template('centrum_index.html')

    @admin_bp.route('/admin/centrum/audyt')
    @dynamic_role_required('ustawienia')
    def admin_centrum_audyt():
        from app.services.agro_warehouse_service import AgroWarehouseService

        linia = request.args.get('linia', 'Agro')
        history = AgroWarehouseService.get_history(limit=50, linia=linia)
        return render_template('centrum_audyt.html', history=history)

    @admin_bp.route('/admin/ustawienia')
    @dynamic_role_required('ustawienia')
    def admin_ustawienia():
        return render_template('ustawienia_index.html')

    @admin_bp.route('/admin/ustawienia/zalogowani')
    @dynamic_role_required('ustawienia')
    def admin_ustawienia_zalogowani():
        online_users = list_online_users(active_within_minutes=30)
        return render_template('ustawienia_zalogowani.html', online_users=online_users, active_window_minutes=30)

    @admin_bp.route('/admin/api/online-users')
    @dynamic_role_required('ustawienia')
    def admin_online_users_api():
        online_users = list_online_users(active_within_minutes=30)
        result = []
        for row in online_users:
            logged_in_at = row.get('logged_in_at')
            last_seen = row.get('last_seen')
            result.append(
                {
                    'session_id': row.get('session_id'),
                    'user_id': row.get('user_id'),
                    'login': row.get('login'),
                    'rola': row.get('rola'),
                    'display_name': row.get('display_name') or row.get('login'),
                    'ip_address': row.get('ip_address') or '',
                    'last_path': row.get('last_path') or '',
                    'logged_in_at': logged_in_at.strftime('%Y-%m-%d %H:%M:%S') if logged_in_at else '',
                    'last_seen': last_seen.strftime('%Y-%m-%d %H:%M:%S') if last_seen else '',
                    'idle_seconds': int(row.get('idle_seconds') or 0),
                    'is_active': bool(row.get('is_active')),
                }
            )
        return jsonify({'success': True, 'online_users': result, 'active_window_minutes': 30})