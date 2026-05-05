from datetime import date

from flask import current_app, jsonify, request

from app.db import get_db_connection, get_table_name
from app.decorators import roles_required
from app.services.planning_service import PlanningService


def register_planista_rollover_routes(planista_bp):
    @planista_bp.route('/api/przenies_niezrealizowane', methods=['POST'])
    @roles_required('planista', 'admin', 'zarzad')
    def api_przenies_niezrealizowane():
        """Move incomplete plans to next day, creating new Zasyp and Workowanie plans."""
        current_app.logger.debug('api_przenies_niezrealizowane called')

        try:
            data_dict = request.get_json() or {}
            current_data = data_dict.get('data')
            current_app.logger.debug(f'[PRZENIES API] Request body: {data_dict}')
            current_app.logger.debug(f'[PRZENIES API] Extracted current_data: {current_data} (type: {type(current_data).__name__})')

            if not current_data:
                current_app.logger.warning('[PRZENIES API] Data is missing!')
                return jsonify({'success': False, 'message': 'Data jest wymagana'}), 400

            linia = data_dict.get('linia') or 'PSD'
            success, message, count = PlanningService.przenies_niezrealizowane(current_data, linia=linia)

            if success:
                return jsonify({'success': True, 'message': message, 'count': count}), 200

            return jsonify({'success': False, 'message': message}), 400

        except Exception as error:
            current_app.logger.exception(f'Error in api_przenies_niezrealizowane: {str(error)}')
            return jsonify({'success': False, 'message': f'Błąd serwera: {str(error)}'}), 500

    @planista_bp.route('/api/check_niezrealizowane', methods=['POST', 'GET'])
    @roles_required('planista', 'admin', 'zarzad')
    def api_check_niezrealizowane():
        """Check what incomplete plans exist and would be moved."""
        try:
            if request.method == 'POST':
                data_dict = request.get_json() or {}
                current_data = data_dict.get('data')
                linia = data_dict.get('linia') or 'PSD'
            else:
                current_data = request.args.get('data')
                linia = request.args.get('linia') or 'PSD'

            if not current_data:
                current_data = date.today().strftime('%Y-%m-%d')

            table_plan = get_table_name('plan_produkcji', linia)
            table_bufor = get_table_name('bufor', linia)

            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute(
                f"""
                SELECT z.id AS zasyp_id, z.produkt,
                       COALESCE(z.tonaz, 0) AS z_plan,
                       COALESCE(z.tonaz_rzeczywisty, 0) AS z_real,
                       w.id AS workowanie_id,
                       COALESCE(w.tonaz, 0) AS w_plan,
                       COALESCE(w.tonaz_rzeczywisty, 0) AS w_real
                FROM {table_plan} z
                LEFT JOIN {table_plan} w
                    ON w.zasyp_id = z.id AND LOWER(w.sekcja) = 'workowanie'
                WHERE DATE(z.data_planu) = %s
                  AND z.status = 'zakonczone'
                  AND LOWER(z.sekcja) = 'zasyp'
                  AND COALESCE(z.typ_zlecenia, '') != 'carry_over_ghost'
                ORDER BY z.id
            """,
                (current_data,),
            )

            all_plans = cursor.fetchall()
            bufor_remaining_by_zasyp_id = {}
            try:
                zasyp_ids = sorted({int(plan['zasyp_id']) for plan in all_plans if plan.get('zasyp_id')})
                if zasyp_ids:
                    placeholders = ','.join(['%s'] * len(zasyp_ids))
                    cursor.execute(
                        f"""
                        SELECT zasyp_id,
                               COALESCE(SUM(tonaz_rzeczywisty), 0) AS buf_tonaz_rzeczywisty,
                               COALESCE(SUM(spakowano), 0) AS buf_spakowano
                        FROM {table_bufor}
                        WHERE DATE(data_planu) = %s
                          AND status = 'aktywny'
                          AND zasyp_id IN ({placeholders})
                        GROUP BY zasyp_id
                        """,
                        tuple([current_data] + zasyp_ids),
                    )
                    for row in cursor.fetchall():
                        try:
                            zasyp_id = int(row.get('zasyp_id'))
                        except Exception:
                            continue
                        bufor_total = float(row.get('buf_tonaz_rzeczywisty') or 0.0)
                        bufor_packed = float(row.get('buf_spakowano') or 0.0)
                        bufor_remaining_by_zasyp_id[zasyp_id] = max(0.0, bufor_total - bufor_packed)
            except Exception:
                bufor_remaining_by_zasyp_id = {}

            conn.close()

            details = []
            total_remaining = 0.0

            from datetime import datetime, timedelta

            current_date_obj = datetime.strptime(current_data, '%Y-%m-%d')
            next_date = current_date_obj + timedelta(days=1)
            next_data_str = next_date.strftime('%Y-%m-%d')

            for plan in all_plans:
                zasyp_id = int(plan['zasyp_id'])
                w_plan = float(plan['w_plan'] or 0.0)
                w_real = float(plan['w_real'] or 0.0)
                z_plan = float(plan['z_plan'] or 0.0)
                z_real = float(plan['z_real'] or 0.0)
                has_linked_workowanie = bool(plan.get('workowanie_id'))

                rem_kg = max(0.0, w_plan - w_real)
                in_buf_kg = max(0.0, z_real - w_real) if has_linked_workowanie else 0.0
                short_kg = max(0.0, w_plan - z_real)
                z_short = max(0.0, z_plan - z_real)

                buf_rem = float(bufor_remaining_by_zasyp_id.get(zasyp_id, 0.0) or 0.0)

                if buf_rem > 0:
                    effective_rem = buf_rem
                elif rem_kg > 0:
                    effective_rem = rem_kg
                elif in_buf_kg > 0:
                    effective_rem = in_buf_kg
                elif z_short > 0:
                    effective_rem = z_short
                else:
                    continue

                total_remaining += effective_rem
                details.append(
                    {
                        'plan_id': int(plan['zasyp_id']),
                        'produkt': str(plan['produkt']),
                        'w_plan_kg': float(max(z_plan, w_plan)),
                        'w_real_kg': float(w_real),
                        'remaining_kg': float(effective_rem),
                        'shortfall_kg': float(short_kg),
                        'in_buffer_kg': float(buf_rem if buf_rem > 0 else in_buf_kg),
                        'zasyp_shortfall_kg': float(z_short),
                    }
                )

            if not details:
                return jsonify({'success': False, 'message': 'Brak zleceń do przeniesienia.'}), 400

            return jsonify(
                {
                    'success': True,
                    'current_data': current_data,
                    'next_date': next_data_str,
                    'current_date_formatted': current_date_obj.strftime('%d.%m.%Y'),
                    'next_date_formatted': next_date.strftime('%d.%m.%Y'),
                    'plans': details,
                    'total_remaining_kg': float(total_remaining),
                    'count': len(details),
                }
            ), 200

        except Exception as error:
            current_app.logger.exception(f'Error in api_check_niezrealizowane: {str(error)}')
            return jsonify({'success': False, 'message': f'Błąd serwera: {str(error)}'}), 500

    @planista_bp.route('/api/check_zlecenie', methods=['POST', 'GET'])
    @roles_required('planista', 'admin', 'zarzad')
    def api_check_zlecenie():
        """Check given plan and report which parts are still active or not closed."""
        try:
            plan_id = request.args.get('plan_id') or request.form.get('plan_id')
            linia = request.args.get('linia') or request.form.get('linia', 'PSD')

            if not plan_id:
                return jsonify({'success': False, 'message': 'Brak plan_id'}), 400
            try:
                plan_id = int(plan_id)
            except Exception:
                return jsonify({'success': False, 'message': 'Nieprawidłowe plan_id'}), 400

            table_plan = get_table_name('plan_produkcji', linia)
            table_szarze = get_table_name('szarze', linia)
            table_pal = get_table_name('palety_workowanie', linia)
            table_bufor = get_table_name('bufor', linia)

            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute(
                f"SELECT id, sekcja, produkt, tonaz, tonaz_rzeczywisty, status, real_start, real_stop FROM {table_plan} WHERE id = %s",
                (plan_id,),
            )
            plan = cursor.fetchone()
            if not plan:
                conn.close()
                return jsonify({'success': False, 'message': 'Zlecenie nie znalezione'}), 404

            plan_ton = float(plan.get('tonaz') or 0)
            real_ton = float(plan.get('tonaz_rzeczywisty') or 0)
            remaining = max(0.0, plan_ton - real_ton)

            related = {}
            try:
                if (plan.get('sekcja') or '').strip().lower() == 'zasyp':
                    cursor.execute(
                        f"SELECT id, sekcja, tonaz, tonaz_rzeczywisty, status FROM {table_plan} WHERE zasyp_id = %s AND LOWER(sekcja) = 'workowanie' LIMIT 1",
                        (plan_id,),
                    )
                    workowanie = cursor.fetchone()
                    if workowanie:
                        w_ton = float(workowanie.get('tonaz') or 0)
                        w_real = float(workowanie.get('tonaz_rzeczywisty') or 0)
                        related['workowanie'] = {
                            'id': workowanie.get('id'),
                            'sekcja': workowanie.get('sekcja'),
                            'plan_kg': w_ton,
                            'real_kg': w_real,
                            'remaining_kg': max(0.0, w_ton - w_real),
                            'status': workowanie.get('status'),
                        }

                cursor.execute(f"SELECT COALESCE(SUM(waga),0) AS szarze_sum FROM {table_szarze} WHERE plan_id = %s", (plan_id,))
                row = cursor.fetchone()
                related['szarze_sum_kg'] = float(row.get('szarze_sum') or 0)

                cursor.execute(f"SELECT COUNT(*) AS count, COALESCE(SUM(waga),0) AS total_kg FROM {table_pal} WHERE plan_id = %s", (plan_id,))
                row = cursor.fetchone()
                related['palety_count'] = int(row.get('count') or 0)
                related['palety_total_kg'] = float(row.get('total_kg') or 0)

                cursor.execute(
                    f"SELECT id, zasyp_id, data_planu, produkt, spakowano, status FROM {table_bufor} WHERE zasyp_id = %s OR plan_id = %s",
                    (plan_id, plan_id),
                )
                related['bufor'] = cursor.fetchall() or []
            except Exception:
                current_app.logger.exception('Error gathering related info for plan')

            conn.close()

            is_active = False
            reasons = []
            if (plan.get('status') or '').strip().lower() != 'zakonczone':
                is_active = True
                reasons.append('status != zakonczone')
            if remaining > 0:
                is_active = True
                reasons.append(f'Nie spakowano {remaining:.1f} kg')
            if related.get('bufor'):
                for buffer_row in related.get('bufor'):
                    if (buffer_row.get('status') or '').strip().lower() != 'zamkniete' and (
                        buffer_row.get('spakowano') is None or float(buffer_row.get('spakowano') or 0) < 0.0001
                    ):
                        is_active = True
                        reasons.append('Istnieją aktywne wpisy w buforze')
                        break

            return jsonify(
                {
                    'success': True,
                    'plan': {
                        'id': plan.get('id'),
                        'sekcja': plan.get('sekcja'),
                        'produkt': plan.get('produkt'),
                        'status': plan.get('status'),
                        'plan_kg': plan_ton,
                        'real_kg': real_ton,
                        'remaining_kg': remaining,
                    },
                    'related': related,
                    'active': is_active,
                    'reasons': reasons,
                }
            ), 200

        except Exception as error:
            current_app.logger.exception(f'Error in api_check_zlecenie: {str(error)}')
            return jsonify({'success': False, 'message': f'Błąd serwera: {str(error)}'}), 500

    @planista_bp.route('/api/przenies_wybrane_zlecenia', methods=['POST'])
    @roles_required('planista', 'admin', 'zarzad')
    def api_przenies_wybrane_zlecenia():
        """Move selected incomplete plans to next day."""
        try:
            data_dict = request.get_json() or {}
            current_data = data_dict.get('data')
            plan_ids = data_dict.get('plan_ids', [])

            if not current_data:
                return jsonify({'success': False, 'message': 'Data jest wymagana'}), 400

            if not plan_ids or not isinstance(plan_ids, list):
                return jsonify({'success': False, 'message': 'Wybierz przynajmniej jedno zlecenie'}), 400

            linia = data_dict.get('linia') or 'PSD'
            success, message, _count = PlanningService.przenies_niezrealizowane(
                current_data,
                plan_ids_to_move=plan_ids,
                linia=linia,
            )

            if success:
                response_message = message or 'Operacja zakończona pomyślnie.'
                return jsonify({'success': True, 'message': response_message}), 200

            return jsonify({'success': False, 'message': message}), 400

        except Exception as error:
            current_app.logger.exception(f'Error in api_przenies_wybrane_zlecenia: {str(error)}')
            return jsonify({'success': False, 'message': f'Błąd serwera: {str(error)}'}), 500