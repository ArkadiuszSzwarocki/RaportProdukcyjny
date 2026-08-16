
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from app.services.inwentaryzacja_produkcji_service import InwentaryzacjaProdukcjiService
from app.db import get_db_connection
from app.decorators import roles_required

inwentaryzacja_produkcji_bp = Blueprint(
    'inwentaryzacja_produkcji', __name__,
    url_prefix='/produkcja/inwentaryzacja'
)


@inwentaryzacja_produkcji_bp.route('/')
def index():
    active_sessions = InwentaryzacjaProdukcjiService.get_active_sessions()

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM produkcja_inwentaryzacja_sesje ORDER BY id DESC LIMIT 500")
    sessions = cursor.fetchall()
    conn.close()

    return render_template(
        'inwentaryzacja_produkcji/index.html',
        active_sessions=active_sessions,
        sessions=sessions,
    )


@inwentaryzacja_produkcji_bp.route('/start', methods=['POST'])
def start():
    typ = request.form.get('typ', 'BB_MZ').strip().upper()
    comment = request.form.get('comment', '')

    if typ not in ('BB_MZ', 'KO'):
        return "Nieprawidłowy typ inwentaryzacji", 400

    success, result = InwentaryzacjaProdukcjiService.start_session(
        typ, session.get('login', 'system'), comment
    )
    if success:
        return redirect(url_for('inwentaryzacja_produkcji.skaner', sesja_id=result))
    return f"Błąd: {result}", 400


@inwentaryzacja_produkcji_bp.route('/skaner/<int:sesja_id>')
def skaner(sesja_id):
    sesja = InwentaryzacjaProdukcjiService.get_session(sesja_id)
    if not sesja:
        return "Sesja nie istnieje", 404

    typ = sesja.get('typ', 'BB_MZ')
    tanks = InwentaryzacjaProdukcjiService.get_tanks_status(sesja_id, typ)

    return render_template(
        'inwentaryzacja_produkcji/skaner.html',
        sesja_id=sesja_id,
        sesja=sesja,
        tanks=tanks,
        typ=typ,
    )


@inwentaryzacja_produkcji_bp.route('/api/zapisz-wpis', methods=['POST'])
def zapisz_wpis():
    data = request.json
    success, msg = InwentaryzacjaProdukcjiService.save_entry(
        data['sesja_id'],
        data.get('zbiornik'),
        data.get('nazwa', ''),
        data.get('nr_partii', ''),
        data.get('waga', 0),
        data.get('komentarz', ''),
        session.get('login', 'system'),
    )
    return jsonify({"success": success, "message": msg})


@inwentaryzacja_produkcji_bp.route('/api/status-zbiornikow', methods=['POST'])
def status_zbiornikow():
    data = request.json
    sesja_id = data.get('sesja_id')
    typ = data.get('typ', 'BB_MZ')
    tanks = InwentaryzacjaProdukcjiService.get_tanks_status(sesja_id, typ)
    return jsonify({"success": True, "tanks": tanks})


@inwentaryzacja_produkcji_bp.route('/api/podpowiedzi-nazw', methods=['GET'])
def podpowiedzi_nazw():
    names = InwentaryzacjaProdukcjiService.get_all_product_names()
    return jsonify({"success": True, "names": names})


@inwentaryzacja_produkcji_bp.route('/raport/<int:sesja_id>')
def raport(sesja_id):
    entries = InwentaryzacjaProdukcjiService.get_report(sesja_id)
    sesja = InwentaryzacjaProdukcjiService.get_session(sesja_id)
    role = (session.get('rola') or '').lower().replace(' ', '').replace('_', '').replace('-', '').strip()

    return render_template(
        'inwentaryzacja_produkcji/raport.html',
        entries=entries,
        sesja=sesja,
        role=role,
    )


@inwentaryzacja_produkcji_bp.route('/api/zamknij-sesje', methods=['POST'])
def zamknij_sesje():
    sesja_id = request.json.get('sesja_id')
    success, msg = InwentaryzacjaProdukcjiService.close_session(sesja_id)
    return jsonify({"success": success, "message": msg})


@inwentaryzacja_produkcji_bp.route('/api/zatwierdz-inwentaryzacje', methods=['POST'])
@roles_required('lider', 'admin', 'masteradmin', 'kierownik', 'zarzad')
def zatwierdz_inwentaryzacje():
    sesja_id = request.json.get('sesja_id')
    success, msg = InwentaryzacjaProdukcjiService.apply_inventory(
        sesja_id, session.get('login', 'system')
    )
    return jsonify({"success": success, "message": msg})


@inwentaryzacja_produkcji_bp.route('/api/edytuj-sesje', methods=['POST'])
def edytuj_sesje():
    data = request.json
    sesja_id = data.get('sesja_id')
    comment = data.get('comment')
    success, msg = InwentaryzacjaProdukcjiService.update_session(sesja_id, comment)
    return jsonify({"success": success, "message": msg})


@inwentaryzacja_produkcji_bp.route('/api/usun-sesje', methods=['POST'])
@roles_required('lider', 'admin', 'masteradmin', 'kierownik', 'zarzad')
def usun_sesje():
    sesja_id = request.json.get('sesja_id')
    success, msg = InwentaryzacjaProdukcjiService.delete_session(sesja_id)
    return jsonify({"success": success, "message": msg})


@inwentaryzacja_produkcji_bp.route('/api/wznow-sesje', methods=['POST'])
def wznow_sesje():
    sesja_id = request.json.get('sesja_id')
    success, msg = InwentaryzacjaProdukcjiService.resume_session(sesja_id)
    return jsonify({"success": success, "message": msg})


@inwentaryzacja_produkcji_bp.route('/api/cofnij-zatwierdzenie', methods=['POST'])
@roles_required('lider', 'admin', 'masteradmin', 'kierownik', 'zarzad')
def cofnij_zatwierdzenie():
    sesja_id = request.json.get('sesja_id')
    success, msg = InwentaryzacjaProdukcjiService.revert_session(sesja_id)
    return jsonify({"success": success, "message": msg})
