
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from app.services.inwentaryzacja_service import InwentaryzacjaService
from app.db import get_db_connection, get_table_name
from app.decorators import masteradmin_required

inwentaryzacja_bp = Blueprint('inwentaryzacja', __name__, url_prefix='/magazyn/inwentaryzacja')

@inwentaryzacja_bp.route('/')
def index():
    active_sessions = InwentaryzacjaService.get_active_sessions()
    
    # Get recent sessions ordered strictly by newest first (id DESC)
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM magazyn_inwentaryzacja_sesje ORDER BY id DESC LIMIT 500")
    sessions = cursor.fetchall()
    conn.close()
    
    return render_template('inwentaryzacja/index.html', active_sessions=active_sessions, sessions=sessions)

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
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM magazyn_inwentaryzacja_sesje WHERE id = %s", (sesja_id,))
    sesja = cursor.fetchone()
    conn.close()
    
    target_lokalizacja = sesja.get('lokalizacja') if sesja else 'WSZYSTKO'
    return render_template('inwentaryzacja/skaner.html', sesja_id=sesja_id, target_lokalizacja=target_lokalizacja)

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
        data.get('typ_opakowania', 'brak'),
        data.get('jednostka', 'kg')
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
    
    role = (session.get('rola') or '').lower().replace(' ', '').replace('_', '').replace('-', '').strip()
    
    return render_template('inwentaryzacja/raport.html', entries=entries, sesja=sesja, role=role)

@inwentaryzacja_bp.route('/api/lookup-pallet', methods=['GET'])
def lookup_pallet():
    code = request.args.get('code', '').strip().upper()
    if not code:
        return jsonify({"success": False, "message": "Brak kodu"})
        
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    pallet = None
    
    # Clean code: if it starts with prefix like SUR-, OPK-, DOD-, PAL-
    clean_id = None
    code_prefix = None
    if '-' in code:
        parts = code.split('-')
        if parts:
            code_prefix = parts[0]
        if len(parts) > 1 and parts[1].isdigit():
            clean_id = int(parts[1])
            
    # 1. Search in surowce
    if clean_id and code_prefix == 'SUR':
        cursor.execute("SELECT id, nr_palety, nazwa, nr_partii, stan_magazynowy, data_produkcji, data_przydatnosci, typ_opakowania, 'surowiec' as typ_palety, linia, jednostka FROM magazyn_surowce WHERE id = %s", (clean_id,))
        pallet = cursor.fetchone()
    else:
        cursor.execute("SELECT id, nr_palety, nazwa, nr_partii, stan_magazynowy, data_produkcji, data_przydatnosci, typ_opakowania, 'surowiec' as typ_palety, linia, jednostka FROM magazyn_surowce WHERE nr_palety = %s", (code,))
        pallet = cursor.fetchone()
        
    # 2. Search in opakowania
    if not pallet:
        # Legacy compatibility: accept old OPA-* IDs and normalize them to opakowania.
        if clean_id and code_prefix in ('OPK', 'OPA'):
            cursor.execute("SELECT id, nr_palety, nazwa, nr_partii, stan_magazynowy, data_produkcji, data_przydatnosci, typ_opakowania, 'opakowanie' as typ_palety, linia, 'szt' as jednostka FROM magazyn_opakowania WHERE id = %s", (clean_id,))
            pallet = cursor.fetchone()
        else:
            cursor.execute("SELECT id, nr_palety, nazwa, nr_partii, stan_magazynowy, data_produkcji, data_przydatnosci, typ_opakowania, 'opakowanie' as typ_palety, linia, 'szt' as jednostka FROM magazyn_opakowania WHERE nr_palety = %s", (code,))
            pallet = cursor.fetchone()

    # 3. Search in dodatki
    if not pallet:
        if clean_id and code_prefix == 'DOD':
            cursor.execute("SELECT id, nr_palety, nazwa, nr_partii, stan_magazynowy, data_produkcji, data_przydatnosci, 'brak' as typ_opakowania, 'dodatek' as typ_palety, linia, 'kg' as jednostka FROM magazyn_dodatki WHERE id = %s", (clean_id,))
            pallet = cursor.fetchone()
        else:
            cursor.execute("SELECT id, nr_palety, nazwa, nr_partii, stan_magazynowy, data_produkcji, data_przydatnosci, 'brak' as typ_opakowania, 'dodatek' as typ_palety, linia, 'kg' as jednostka FROM magazyn_dodatki WHERE nr_palety = %s", (code,))
            pallet = cursor.fetchone()
            
    # 4. Search in wyroby gotowe (PSD / AGRO)
    if not pallet:
        hall_contexts = ['PSD', 'AGRO']
        for hall in hall_contexts:
            table = get_table_name('magazyn_palety', hall)
            if clean_id and code_prefix in ('PAL', 'PAT'):
                cursor.execute(f"SELECT id, nr_palety, produkt as nazwa, nr_partii, waga_netto as stan_magazynowy, data_produkcji, data_przydatnosci, typ_opakowania, 'wyrób gotowy' as typ_palety, linia, 'kg' as jednostka FROM {table} WHERE id = %s", (clean_id,))
                pallet = cursor.fetchone()
            else:
                cursor.execute(f"SELECT id, nr_palety, produkt as nazwa, nr_partii, waga_netto as stan_magazynowy, data_produkcji, data_przydatnosci, typ_opakowania, 'wyrób gotowy' as typ_palety, linia, 'kg' as jednostka FROM {table} WHERE nr_palety = %s", (code,))
                pallet = cursor.fetchone()
            if pallet:
                break
                
    conn.close()
    
    if pallet:
        # Format dates as YYYY-MM-DD
        if pallet.get('data_produkcji') and hasattr(pallet['data_produkcji'], 'strftime'):
            pallet['data_produkcji'] = pallet['data_produkcji'].strftime('%Y-%m-%d')
        if pallet.get('data_przydatnosci') and hasattr(pallet['data_przydatnosci'], 'strftime'):
            pallet['data_przydatnosci'] = pallet['data_przydatnosci'].strftime('%Y-%m-%d')
            
        return jsonify({"success": True, "pallet": pallet})
    else:
        return jsonify({"success": False, "message": "Nie znaleziono palety o takim kodzie/SSCC"})

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
    
@inwentaryzacja_bp.route('/api/edytuj-sesje', methods=['POST'])
def edytuj_sesje():
    data = request.json
    sesja_id = data.get('sesja_id')
    lokalizacja = data.get('lokalizacja')
    comment = data.get('comment')
    success, msg = InwentaryzacjaService.update_session(sesja_id, lokalizacja, comment)
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
    
@inwentaryzacja_bp.route('/api/cofnij-zatwierdzenie', methods=['POST'])
def cofnij_zatwierdzenie():
    sesja_id = request.json.get('sesja_id')
    success, msg = InwentaryzacjaService.revert_session(sesja_id)
    return jsonify({"success": success, "message": msg})

