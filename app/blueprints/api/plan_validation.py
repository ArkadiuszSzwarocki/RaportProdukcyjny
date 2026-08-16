from datetime import datetime

from flask import current_app, jsonify, request

from app.db import get_db_connection, get_table_name
from app.decorators import login_required, roles_required


def register_api_plan_validation_routes(api_bp):
    @api_bp.route('/api/validate_plan_anomalies', methods=['POST'])
    @login_required
    @roles_required(['admin', 'lider'])
    def validate_plan_anomalies():
        """Scan and fix plan anomalies for production plans."""
        try:
            from app.services.planning.status import PlanningStatusService

            success, message, fixed_count = PlanningStatusService.validate_and_fix_anomalies()
            return jsonify(
                {
                    'success': success,
                    'message': message,
                    'fixed_count': fixed_count,
                    'timestamp': datetime.now().isoformat(),
                }
            ), 200 if success else 400
        except Exception as error:
            current_app.logger.exception('Error in validate_plan_anomalies: %s', error)
            return jsonify({'success': False, 'message': f'Błąd serwera: {str(error)}'}), 500

    @api_bp.route('/api/plan/<int:plan_id>/check_status', methods=['GET'])
    @login_required
    def check_plan_status(plan_id):
        """Return current plan status details together with anomaly detection output."""
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            linia = request.args.get('linia', 'PSD')
            table_plan = get_table_name('plan_produkcji', linia)
            cursor.execute(
                f"""
                SELECT id, produkt, status, tonaz, tonaz_rzeczywisty, real_start, real_stop, sekcja
                FROM {table_plan}
                WHERE id=%s
                """,
                (plan_id,),
            )
            plan = cursor.fetchone()
            conn.close()

            if not plan:
                return jsonify({'success': False, 'message': f'Plan {plan_id} nie istnieje'}), 404

            tonaz_rzeczywisty = plan['tonaz_rzeczywisty'] or 0
            has_anomaly = tonaz_rzeczywisty > 0 and plan['status'] == 'zaplanowane' and not plan['real_start']
            return jsonify(
                {
                    'success': True,
                    'plan_id': plan['id'],
                    'produkt': plan['produkt'],
                    'status': plan['status'],
                    'tonaz_plan': plan['tonaz'],
                    'tonaz_rzeczywisty': tonaz_rzeczywisty,
                    'real_start': plan['real_start'],
                    'real_stop': plan['real_stop'],
                    'sekcja': plan['sekcja'],
                    'has_status_anomaly': has_anomaly,
                    'anomaly_description': (
                        'Plan has tonaz_rzeczywisty but status is zaplanowane (not yet started)'
                        if has_anomaly
                        else 'No anomalies detected'
                    ),
                }
            ), 200
        except Exception as error:
            current_app.logger.exception('Error checking plan status: %s', error)
            return jsonify({'success': False, 'message': f'Błąd serwera: {str(error)}'}), 500