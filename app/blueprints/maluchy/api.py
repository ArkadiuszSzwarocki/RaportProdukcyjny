from flask import jsonify, request, session
from app.blueprints.maluchy.blueprint import maluchy_bp
from app.decorators import login_required
from app.services.bucket_maluch_service import BucketMaluchService


@maluchy_bp.route('/api/start', methods=['POST'])
@login_required
def api_start_bucket():
    data = request.get_json(silent=True) or request.form
    kod_wiadra = data.get('kod_wiadra', '')
    plan_id = data.get('plan_id')
    linia = data.get('linia') or session.get('selected_hall_view') or 'PSD'
    operator_login = session.get('login') or session.get('imie_nazwisko') or 'operator'

    if not kod_wiadra:
        return jsonify({'success': False, 'message': 'Podaj numer lub zeskanuj kod wiadra!'}), 400
    if not plan_id:
        return jsonify({'success': False, 'message': 'Wybierz lub zeskanuj aktywne zlecenie!'}), 400

    try:
        plan_id = int(plan_id)
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Nieprawidłowe ID zlecenia'}), 400

    success, msg, bucket = BucketMaluchService.start_bucket(
        kod_wiadra=kod_wiadra,
        plan_id=plan_id,
        linia=linia,
        operator_login=operator_login
    )
    status_code = 200 if success else 400
    return jsonify({'success': success, 'message': msg, 'bucket': bucket}), status_code


@maluchy_bp.route('/api/station-material', methods=['GET'])
@login_required
def api_get_station_material():
    stacja_kod = request.args.get('stacja', '')
    linia = request.args.get('linia') or session.get('selected_hall_view') or 'PSD'
    material = BucketMaluchService.get_station_material(stacja_kod, linia)
    return jsonify({'success': True, 'stacja': stacja_kod, 'surowiec': material})


@maluchy_bp.route('/api/item/add', methods=['POST'])
@login_required
def api_add_item():
    data = request.get_json(silent=True) or request.form
    bucket_id = data.get('bucket_id')
    stacja_kod = data.get('stacja_kod', '')
    surowiec_nazwa = data.get('surowiec_nazwa')
    waga = data.get('waga', 0)
    linia = data.get('linia') or session.get('selected_hall_view') or 'PSD'
    operator_login = session.get('login') or session.get('imie_nazwisko') or 'operator'

    if not bucket_id:
        return jsonify({'success': False, 'message': 'Brak ID wiadra'}), 400
    if not stacja_kod:
        return jsonify({'success': False, 'message': 'Zeskanuj lub wybierz stację KO!'}), 400

    try:
        bucket_id = int(bucket_id)
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Nieprawidłowe ID wiadra'}), 400

    success, msg, bucket = BucketMaluchService.add_item_to_bucket(
        bucket_id=bucket_id,
        stacja_kod=stacja_kod,
        surowiec_nazwa=surowiec_nazwa,
        waga=waga,
        operator_login=operator_login,
        linia=linia
    )
    status_code = 200 if success else 400
    return jsonify({'success': success, 'message': msg, 'bucket': bucket}), status_code


@maluchy_bp.route('/api/item/remove', methods=['POST'])
@login_required
def api_remove_item():
    data = request.get_json(silent=True) or request.form
    item_id = data.get('item_id')
    bucket_id = data.get('bucket_id')

    if not item_id or not bucket_id:
        return jsonify({'success': False, 'message': 'Brak parametrów do usunięcia'}), 400

    try:
        item_id = int(item_id)
        bucket_id = int(bucket_id)
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Nieprawidłowe identyfikatory'}), 400

    success, msg, bucket = BucketMaluchService.remove_item_from_bucket(item_id, bucket_id)
    return jsonify({'success': success, 'message': msg, 'bucket': bucket})


@maluchy_bp.route('/api/complete', methods=['POST'])
@login_required
def api_complete_bucket():
    data = request.get_json(silent=True) or request.form
    bucket_id = data.get('bucket_id')
    operator_login = session.get('login') or session.get('imie_nazwisko') or 'operator'

    if not bucket_id:
        return jsonify({'success': False, 'message': 'Brak ID wiadra'}), 400

    try:
        bucket_id = int(bucket_id)
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Nieprawidłowe ID wiadra'}), 400

    success, msg, bucket = BucketMaluchService.complete_bucket(bucket_id, operator_login)
    status_code = 200 if success else 400
    return jsonify({'success': success, 'message': msg, 'bucket': bucket}), status_code


@maluchy_bp.route('/api/delete', methods=['POST'])
@login_required
def api_delete_bucket():
    data = request.get_json(silent=True) or request.form
    bucket_id = data.get('bucket_id')
    operator_login = session.get('login') or session.get('imie_nazwisko') or 'operator'

    if not bucket_id:
        return jsonify({'success': False, 'message': 'Brak ID wiadra'}), 400

    try:
        bucket_id = int(bucket_id)
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Nieprawidłowe ID wiadra'}), 400

    success, msg = BucketMaluchService.delete_bucket(bucket_id, operator_login)
    status_code = 200 if success else 400
    return jsonify({'success': success, 'message': msg}), status_code


@maluchy_bp.route('/api/dump-to-mixer', methods=['POST'])
@login_required
def api_dump_to_mixer():
    data = request.get_json(silent=True) or request.form
    kod_wiadra = data.get('kod_wiadra', '')
    plan_id = data.get('plan_id')
    szarza_id = data.get('szarza_id')
    mieszalnik_kod = data.get('mieszalnik_kod') or data.get('lokalizacja_mieszalnika') or 'MI01'
    linia = data.get('linia') or session.get('selected_hall_view') or 'PSD'
    operator_login = session.get('login') or session.get('imie_nazwisko') or 'operator'

    if not kod_wiadra:
        return jsonify({'success': False, 'message': 'Zeskanuj kod wiadra!'}), 400
    if not plan_id:
        return jsonify({'success': False, 'message': 'Brak identyfikatora zlecenia'}), 400

    try:
        plan_id = int(plan_id)
        if szarza_id:
            szarza_id = int(szarza_id)
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Nieprawidłowe ID zlecenia lub szarży'}), 400

    success, msg, bucket = BucketMaluchService.scan_and_dump_to_mixer(
        kod_wiadra=kod_wiadra,
        plan_id=plan_id,
        szarza_id=szarza_id,
        mieszalnik_kod=mieszalnik_kod,
        operator_login=operator_login,
        linia=linia
    )
    status_code = 200 if success else 400
    return jsonify({'success': success, 'message': msg, 'bucket': bucket}), status_code


@maluchy_bp.route('/api/plan/<int:plan_id>', methods=['GET'])
@login_required
def api_get_plan_summary(plan_id: int):
    linia = request.args.get('linia') or session.get('selected_hall_view') or 'PSD'
    summary = BucketMaluchService.get_plan_maluchy_summary(plan_id, linia)
    return jsonify({'success': True, 'data': summary})
