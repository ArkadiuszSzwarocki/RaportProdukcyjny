
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from app.services.inwentaryzacja_service import InwentaryzacjaService
from app.db import get_db_connection, get_table_name
from app.decorators import roles_required

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

    return render_template(
        'inwentaryzacja/index.html',
        active_sessions=active_sessions,
        sessions=sessions,
    )

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
    typ = request.args.get('typ')
    names = InwentaryzacjaService.get_all_product_names(typ)
    return jsonify({"success": True, "names": names})

@inwentaryzacja_bp.route('/api/lokalizacje', methods=['GET'])
def get_lokalizacje():
    from datetime import datetime, timedelta

    date_from = request.args.get('from') or ''
    date_to = request.args.get('to') or ''

    def _parse_date(val):
        try:
            return datetime.strptime(val, '%Y-%m-%d')
        except Exception:
            return None

    start_date = _parse_date(date_from) or datetime.now()
    end_date = _parse_date(date_to) or start_date
    end_date_exclusive = end_date + timedelta(days=1)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT DISTINCT UPPER(lokalizacja)
        FROM magazyn_inwentaryzacja_sesje
        WHERE created_at >= %s
          AND created_at < %s
          AND lokalizacja IS NOT NULL
          AND lokalizacja <> ''
        ORDER BY UPPER(lokalizacja) ASC
        """,
        (start_date.strftime('%Y-%m-%d'), end_date_exclusive.strftime('%Y-%m-%d')),
    )
    locations = [row[0] for row in cursor.fetchall() if row and row[0]]
    conn.close()

    return jsonify({"success": True, "locations": locations})

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

@inwentaryzacja_bp.route('/api/search-pallets', methods=['GET'])
def search_pallets():
    query = request.args.get('query', '').strip().upper()
    typ = request.args.get('typ', '').strip()
    
    if len(query) < 2:
        return jsonify({"success": True, "pallets": []})
        
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    like_q = f"%{query}%"
    pallets = []
    
    try:
        # Surowce
        if not typ or typ == 'surowiec':
            cursor.execute("SELECT id, nr_palety, nazwa, nr_partii, stan_magazynowy, lokalizacja, data_produkcji, data_przydatnosci, 'surowiec' as typ_palety, linia, jednostka FROM magazyn_surowce WHERE UPPER(nr_palety) LIKE %s OR UPPER(nazwa) LIKE %s OR UPPER(nr_partii) LIKE %s LIMIT 20", (like_q, like_q, like_q))
            pallets.extend(cursor.fetchall())
            
        # Opakowania
        if not typ or typ == 'opakowanie':
            cursor.execute("SELECT id, nr_palety, nazwa, nr_partii, stan_magazynowy, lokalizacja, data_produkcji, data_przydatnosci, 'opakowanie' as typ_palety, linia, 'szt' as jednostka FROM magazyn_opakowania WHERE UPPER(nr_palety) LIKE %s OR UPPER(nazwa) LIKE %s OR UPPER(nr_partii) LIKE %s LIMIT 20", (like_q, like_q, like_q))
            pallets.extend(cursor.fetchall())
            
        # Dodatki
        if not typ or typ == 'dodatek':
            cursor.execute("SELECT id, nr_palety, nazwa, nr_partii, stan_magazynowy, lokalizacja, data_produkcji, data_przydatnosci, 'dodatek' as typ_palety, linia, 'kg' as jednostka FROM magazyn_dodatki WHERE UPPER(nr_palety) LIKE %s OR UPPER(nazwa) LIKE %s OR UPPER(nr_partii) LIKE %s LIMIT 20", (like_q, like_q, like_q))
            pallets.extend(cursor.fetchall())
            
        # Wyroby gotowe
        if not typ or typ == 'wyrób gotowy':
            for hall in ['PSD', 'AGRO']:
                table = get_table_name('magazyn_palety', hall)
                cursor.execute(f"SELECT id, nr_palety, produkt as nazwa, nr_partii, waga_netto as stan_magazynowy, lokalizacja, data_produkcji, data_przydatnosci, 'wyrób gotowy' as typ_palety, linia, 'kg' as jednostka FROM {table} WHERE UPPER(nr_palety) LIKE %s OR UPPER(produkt) LIKE %s OR UPPER(nr_partii) LIKE %s LIMIT 20", (like_q, like_q, like_q))
                pallets.extend(cursor.fetchall())
                
        # Format dates and limit to 30 overall
        for p in pallets[:30]:
            if p.get('data_produkcji') and hasattr(p['data_produkcji'], 'strftime'):
                p['data_produkcji'] = p['data_produkcji'].strftime('%Y-%m-%d')
            if p.get('data_przydatnosci') and hasattr(p['data_przydatnosci'], 'strftime'):
                p['data_przydatnosci'] = p['data_przydatnosci'].strftime('%Y-%m-%d')
                
        return jsonify({"success": True, "pallets": pallets[:30]})
    finally:
        conn.close()

@inwentaryzacja_bp.route('/api/zamknij-sesje', methods=['POST'])
def zamknij_sesje():
    sesja_id = request.json.get('sesja_id')
    success, msg = InwentaryzacjaService.close_session(sesja_id)
    return jsonify({"success": success, "message": msg})

@inwentaryzacja_bp.route('/api/zatwierdz-inwentaryzacje', methods=['POST'])
@roles_required('lider', 'admin', 'masteradmin', 'kierownik', 'zarzad')
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
@roles_required('lider', 'admin', 'masteradmin', 'kierownik', 'zarzad')
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
@roles_required('lider', 'admin', 'masteradmin', 'kierownik', 'zarzad')
def cofnij_zatwierdzenie():
    sesja_id = request.json.get('sesja_id')
    success, msg = InwentaryzacjaService.revert_session(sesja_id)
    return jsonify({"success": success, "message": msg})

@inwentaryzacja_bp.route('/podsumowanie-dnia', methods=['GET'])
def podsumowanie_dnia():
    from datetime import datetime
    
    date_str = request.args.get('date')
    if not date_str:
        date_str = datetime.now().strftime('%Y-%m-%d')
        
    summary = InwentaryzacjaService.get_daily_summary(date_str)
    
    # Przekazanie typów do pętli w Jinja i ładnych nazw
    kategorie = {
        'surowiec': 'Surowce',
        'opakowanie': 'Opakowania',
        'dodatek': 'Dodatki',
        'wyrób gotowy': 'Wyroby Gotowe'
    }
    
    return render_template('inwentaryzacja/podsumowanie_dnia.html', date_str=date_str, summary=summary, kategorie=kategorie)


@inwentaryzacja_bp.route('/drukuj-zbiorczo', methods=['GET'])
def drukuj_zbiorczo():
    from datetime import datetime, timedelta

    date_from = request.args.get('from') or ''
    date_to = request.args.get('to') or ''
    locs = [loc.strip().upper() for loc in request.args.getlist('loc') if loc.strip()]

    def _parse_date(val):
        try:
            return datetime.strptime(val, '%Y-%m-%d')
        except Exception:
            return None

    start_date = _parse_date(date_from) or datetime.now()
    end_date = _parse_date(date_to) or start_date
    end_date_exclusive = end_date + timedelta(days=1)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    where = ["created_at >= %s", "created_at < %s"]
    params = [start_date.strftime('%Y-%m-%d'), end_date_exclusive.strftime('%Y-%m-%d')]

    if locs:
        placeholders = ','.join(['%s'] * len(locs))
        where.append(f"UPPER(lokalizacja) IN ({placeholders})")
        params.extend(locs)

    query = "SELECT * FROM magazyn_inwentaryzacja_sesje WHERE " + " AND ".join(where) + " ORDER BY created_at ASC, id ASC"
    cursor.execute(query, tuple(params))
    sessions = cursor.fetchall()
    conn.close()

    report_items = []
    for sesja in sessions:
        entries = InwentaryzacjaService.get_report(sesja['id'])
        report_items.append({'sesja': sesja, 'entries': entries})

    return render_template(
        'inwentaryzacja/raport_zbiorczy.html',
        report_items=report_items,
        date_from=start_date.strftime('%Y-%m-%d'),
        date_to=end_date.strftime('%Y-%m-%d'),
        selected_locations=locs,
    )

