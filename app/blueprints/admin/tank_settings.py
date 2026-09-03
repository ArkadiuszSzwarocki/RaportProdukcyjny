from flask import request, jsonify, render_template, session
from app.decorators import dynamic_role_required, login_required
from app.services.tank_validation_service import TankValidationService


def register_admin_tank_settings_routes(admin_bp):
    """Register admin routes for production tank assignment & validation configuration."""

    @admin_bp.route('/admin/ustawienia/zbiorniki', methods=['GET'])
    @dynamic_role_required('ustawienia')
    def admin_ustawienia_zbiorniki():
        """Render the tank validation and assignment configuration page."""
        linia = request.args.get('linia', 'Agro')
        from app.repositories.tank_validation_repository import TankValidationRepository
        existing_rules = TankValidationRepository.get_all_rules()
        if not existing_rules:
            # Auto-seed from current active production tanks so rules are enabled immediately
            TankValidationService.populate_from_active_production(linia=linia, user_login='system')
        
        data = TankValidationService.get_all_tanks_with_state(linia=linia)
        return render_template(
            'ustawienia_zbiorniki.html',
            grouped_tanks=data['grouped'],
            items=data['items'],
            dictionary=data['dictionary'],
            linia=linia,
            session_role=session.get('rola', '')
        )

    @admin_bp.route('/admin/api/ustawienia/zbiorniki/data', methods=['GET'])
    @dynamic_role_required('ustawienia')
    def admin_api_zbiorniki_data():
        """Return JSON data of all tanks, rules, and current production status."""
        linia = request.args.get('linia', 'Agro')
        data = TankValidationService.get_all_tanks_with_state(linia=linia)
        return jsonify({'success': True, 'data': data})

    @admin_bp.route('/admin/api/ustawienia/zbiorniki/save', methods=['POST'])
    @dynamic_role_required('ustawienia')
    def admin_api_zbiorniki_save():
        """Save or update validation rule for a single tank or bulk list."""
        payload = request.get_json(silent=True) or {}
        user_login = session.get('login', 'admin')

        # Bulk save
        if 'assignments' in payload and isinstance(payload['assignments'], list):
            saved_count = 0
            for item in payload['assignments']:
                kod = item.get('kod_zbiornika')
                nazwa = item.get('nazwa_surowca', '')
                is_act = bool(item.get('is_active', True))
                opis = item.get('opis', '')
                surowiec_id = item.get('surowiec_id')
                if kod:
                    if not nazwa.strip() and not is_act:
                        TankValidationService.clear_tank_rule(kod)
                    else:
                        TankValidationService.save_tank_rule(
                            kod_zbiornika=kod,
                            nazwa_surowca=nazwa,
                            surowiec_id=surowiec_id,
                            opis=opis,
                            is_active=is_act,
                            user_login=user_login
                        )
                    saved_count += 1
            return jsonify({'success': True, 'message': f'Zapisano konfigurację dla {saved_count} zbiorników.'})

        # Single tank save
        kod = payload.get('kod_zbiornika')
        nazwa = payload.get('nazwa_surowca', '')
        surowiec_id = payload.get('surowiec_id')
        opis = payload.get('opis')
        is_active = bool(payload.get('is_active', True))

        if not kod:
            return jsonify({'success': False, 'message': 'Brak kodu zbiornika.'}), 400

        ok, msg = TankValidationService.save_tank_rule(
            kod_zbiornika=kod,
            nazwa_surowca=nazwa,
            surowiec_id=surowiec_id,
            opis=opis,
            is_active=is_active,
            user_login=user_login
        )
        if ok:
            return jsonify({'success': True, 'message': msg})
        return jsonify({'success': False, 'message': msg}), 400

    @admin_bp.route('/admin/api/ustawienia/zbiorniki/clear', methods=['POST'])
    @dynamic_role_required('ustawienia')
    def admin_api_zbiorniki_clear():
        """Clear assigned rule for a tank."""
        payload = request.get_json(silent=True) or {}
        kod = payload.get('kod_zbiornika')
        if not kod:
            return jsonify({'success': False, 'message': 'Brak kodu zbiornika.'}), 400

        ok, msg = TankValidationService.clear_tank_rule(kod)
        if ok:
            return jsonify({'success': True, 'message': msg})
        return jsonify({'success': False, 'message': msg}), 400

    @admin_bp.route('/admin/api/ustawienia/zbiorniki/populate-current', methods=['POST'])
    @dynamic_role_required('ustawienia')
    def admin_api_zbiorniki_populate():
        """Auto-populate validation rules based on current production snapshot."""
        payload = request.get_json(silent=True) or {}
        linia = payload.get('linia', 'Agro')
        user_login = session.get('login', 'admin')

        ok, msg, count = TankValidationService.populate_from_active_production(linia=linia, user_login=user_login)
        return jsonify({'success': ok, 'message': msg, 'count': count})
