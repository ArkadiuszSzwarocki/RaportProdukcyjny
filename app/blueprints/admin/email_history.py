# File: app/blueprints/admin/email_history.py
"""
Admin Email History Controller.
Provides routes for viewing sent email logs, stats, and manual resends.
"""

from flask import Blueprint, render_template, request, jsonify, session
from datetime import date
from app.services.email_log_service import EmailLogService
from app.decorators import login_required, roles_required


def register_admin_email_history_routes(bp: Blueprint) -> None:
    """Registers email history routes to the admin blueprint."""

    @bp.route('/historia-email', methods=['GET'])
    @bp.route('/admin/historia-email', methods=['GET'])
    @login_required
    @roles_required('admin', 'masteradmin', 'zarzad', 'lider', 'planista')
    def admin_email_history_page():
        """Renders the email history and control panel HTML view."""
        today_str = str(date.today())
        selected_date = request.args.get('data') or today_str
        selected_status = request.args.get('status') or 'ALL'
        selected_line = request.args.get('linia') or 'ALL'

        history_data = EmailLogService.get_history(
            start_date=selected_date,
            end_date=selected_date,
            status=selected_status,
            linia=selected_line,
            limit=50,
            page=1
        )

        return render_template(
            'admin/email_history.html',
            logs=history_data['logs'],
            stats=history_data['stats'],
            total_count=history_data['total_count'],
            selected_date=selected_date,
            selected_status=selected_status,
            selected_line=selected_line
        )

    @bp.route('/api/email-history', methods=['GET'])
    @login_required
    @roles_required('admin', 'masteradmin', 'zarzad', 'lider', 'planista')
    def api_email_history():
        """CQRS Query: Returns JSON email history with dynamic filtering."""
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        status = request.args.get('status')
        linia = request.args.get('linia')
        search_query = request.args.get('search')
        limit = int(request.args.get('limit') or 50)
        page = int(request.args.get('page') or 1)

        result = EmailLogService.get_history(
            start_date=start_date,
            end_date=end_date,
            status=status,
            linia=linia,
            search_query=search_query,
            limit=limit,
            page=page
        )
        return jsonify({'success': True, 'data': result})
