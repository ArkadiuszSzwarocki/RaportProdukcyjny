
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from app.services.inwentaryzacja_service import InwentaryzacjaService
from app.db import get_db_connection
from app.decorators import masteradmin_required

inwentaryzacja_bp = Blueprint('inwentaryzacja', __name__, url_prefix='/magazyn/inwentaryzacja')

@inwentaryzacja_bp.route('/')
def index():
    active_session = InwentaryzacjaService.get_active_session()
    
    # Get recent sessions
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM magazyn_inwentaryzacja_sesje ORDER BY created_at DESC LIMIT 20")
    sessions = cursor.fetchall()
    conn.close()
    
    return render_template('inwentaryzacja/index.html', active_session=active_session, sessions=sessions)

@inwentaryzacja_bp.route('/start', methods=['POST'])
def start():
    comment = request.form.get('comment', '')
    lokalizacja = request.form.get('lokalizacja', 'WSZYSTKO').strip().upper()

    success, result = InwentaryzacjaService.start_session(None, session.get('login', 'system'), comment, lokalizacja)
    if success:

        return redirect(url_for('inwentaryzacja.skaner', sesja_id=result))
    return f"Błąd: {result}", 400

@inwentaryzacja_bp.route('/skaner/<int:sesja_id>')
def skaner(sesja_id):
    return render_template('inwentaryzacja/skaner.html', sesja_id=sesja_id)

@inwentaryzacja_bp.route('/api/szukaj-lokalizacji', methods=['POST'])
def szukaj_lokalizacji():
    data = request.json
    lokalizacja = data.get('lokalizacja', '').strip().upper()
    sesja_id = data.get('sesja_id')
    
    pallets = InwentaryzacjaService.get_pallets_at_location(lokalizacja, sesja_id)
    return jsonify({"success": True, "pallets": pallets})


@inwentaryzacja_bp.route('/api/szukaj-regalu', methods=['POST'])
def szukaj_regalu():
    data = request.json
    prefix = data.get('prefix', '').strip().upper()
    sesja_id = data.get('sesja_id')
    
    rack_data = InwentaryzacjaService.get_rack_data(prefix, sesja_id)
    return jsonify({"success": True, "rack_data": rack_data})


@inwentaryzacja_bp.route('/api/podpowiedzi-nazw', methods=['GET'])
def podpowiedzi_nazw():
    names = InwentaryzacjaService.get_all_product_names()
    return jsonify({"success": True, "names": names})

@inwentaryzacja_bp.route('/api/zapisz-wpis', methods=['POST'])
def zapisz_wpis():
    data = request.json
    success, msg = InwentaryzacjaService.add_entry(
        data['sesja_id'],
        data.get('paleta_id'),
        data.get('typ_palety'),
        data.get('nazwa'),
        data.get('lokalizacja'),
        data.get('nr_partii'),
        data.get('waga_systemowa', 0),
        data.get('waga_faktyczna', 0),
        session.get('login', 'system'),
        data.get('linia', 'PSD'),
        data.get('nr_palety'),
        data.get('data_produkcji'),
        data.get('data_przydatnosci'),
        data.get('typ_opakowania', 'brak')
    )

    return jsonify({"success": success, "message": msg})

@inwentaryzacja_bp.route('/raport/<int:sesja_id>')
def raport(sesja_id):
    entries = InwentaryzacjaService.get_report(sesja_id)
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM magazyn_inwentaryzacja_sesje WHERE id = %s", (sesja_id,))
    sesja = cursor.fetchone()
    conn.close()
    
    return render_template('inwentaryzacja/raport.html', entries=entries, sesja=sesja)

@inwentaryzacja_bp.route('/api/zamknij-sesje', methods=['POST'])
def zamknij_sesje():
    sesja_id = request.json.get('sesja_id')
    success, msg = InwentaryzacjaService.close_session(sesja_id)
    return jsonify({"success": success, "message": msg})

@inwentaryzacja_bp.route('/api/zatwierdz-inwentaryzacje', methods=['POST'])
def zatwierdz_inwentaryzacje():
    sesja_id = request.json.get('sesja_id')
    success, msg = InwentaryzacjaService.apply_inventory(sesja_id, session.get('login', 'system'))
    return jsonify({"success": success, "message": msg})
    
@inwentaryzacja_bp.route('/api/usun-sesje', methods=['POST'])
@masteradmin_required
def usun_sesje():
    sesja_id = request.json.get('sesja_id')
    success, msg = InwentaryzacjaService.delete_session(sesja_id)
    return jsonify({"success": success, "message": msg})

@inwentaryzacja_bp.route('/api/wznow-sesje', methods=['POST'])
def wznow_sesje():
    sesja_id = request.json.get('sesja_id')
    success, msg = InwentaryzacjaService.resume_session(sesja_id)
    return jsonify({"success": success, "message": msg})

