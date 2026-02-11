from flask import Blueprint, request, redirect, url_for, flash, session, render_template, current_app, jsonify
from datetime import date, datetime
from app.db import get_db_connection
from app.decorators import login_required, roles_required
from app.utils.validation import require_field

warehouse_bp = Blueprint('warehouse', __name__)

def bezpieczny_powrot():
    """Default return path: planner view or dashboard"""
    if session.get('rola') == 'planista' or request.form.get('widok_powrotu') == 'planista':
        data = request.form.get('data_planu') or request.form.get('data_powrotu') or request.args.get('data') or str(date.today())
        return url_for('planista.panel_planisty', data=data)
    
    sekcja = request.args.get('sekcja') or request.form.get('sekcja', 'Zasyp')
    data = request.form.get('data_planu') or request.form.get('data_powrotu') or request.args.get('data') or str(date.today())
    return url_for('main.index', sekcja=sekcja, data=data)


@warehouse_bp.route('/dodaj_palete/<int:plan_id>', methods=['POST'])
@login_required
def dodaj_palete(plan_id):
    """Add paleta (package) to Workowanie buffer"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        current_app.logger.info('API dodaj_palete called plan_id=%s', plan_id)
    except Exception:
        pass
    
    try:
        waga_input = int(float(request.form.get('waga_palety', '0').replace(',', '.')))
    except Exception:
        waga_input = 0
    
    cursor.execute("SELECT sekcja, data_planu, produkt FROM plan_produkcji WHERE id=%s", (plan_id,))
    plan_row = cursor.fetchone()
    
    if not plan_row:
        conn.close()
        return ("Błąd: Plan nie znaleziony", 404)
    
    plan_sekcja, plan_data, plan_produkt = plan_row
    
    if plan_sekcja != 'Workowanie':
        conn.close()
        try:
            current_app.logger.warning(f'REJECTED: Cannot add paleta to sekcja={plan_sekcja}')
        except Exception:
            pass
        return ("Błąd: Paletki można dodawać tylko do Workowania (bufora)", 400)
    
    if waga_input <= 0:
        conn.close()
        return ("Błąd: Waga musi być większa od 0", 400)
    
    from datetime import datetime as _dt
    now_ts = _dt.now()
    
    try:
        cursor.execute(
            "INSERT INTO palety_workowanie (plan_id, waga, tara, waga_brutto, data_dodania, status) VALUES (%s, %s, 25, 0, %s, 'do_przyjecia')",
            (plan_id, waga_input, now_ts)
        )
        paleta_id = cursor.lastrowid if hasattr(cursor, 'lastrowid') else None
        
        cursor.execute(
            "UPDATE plan_produkcji SET tonaz_rzeczywisty = COALESCE(tonaz_rzeczywisty, 0) + %s WHERE id = %s",
            (waga_input, plan_id)
        )
        
        conn.commit()
        try:
            current_app.logger.info(f'✓ Added paleta to Workowanie: plan_id={plan_id}, waga={waga_input}kg')
        except Exception:
            pass
        
    except Exception as e:
        try:
            current_app.logger.exception(f'Failed to add paleta: {str(e)}')
        except Exception:
            pass
        conn.rollback()
        conn.close()
        return ("Błąd: Nie udało się dodać paletki", 500)
    
    conn.close()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'message': 'Paletka dodana', 'paleta_id': paleta_id}), 200
    
    return redirect(bezpieczny_powrot())


@warehouse_bp.route('/dodaj_palete_page/<int:plan_id>', methods=['GET'])
@login_required
def dodaj_palete_page(plan_id):
    """Render form for adding paleta"""
    conn = get_db_connection()
    cursor = conn.cursor()
    produkt = None
    sekcja = None
    typ = None
    try:
        cursor.execute("SELECT produkt, sekcja, typ_produkcji FROM plan_produkcji WHERE id=%s", (plan_id,))
        row = cursor.fetchone()
        if row:
            produkt, sekcja, typ = row[0], row[1], row[2]
    except Exception:
        try: current_app.logger.exception('Failed to fetch plan %s for dodaj_palete_page', plan_id)
        except Exception: pass
    finally:
        try: conn.close()
        except Exception: pass
    return render_template('dodaj_palete_popup.html', plan_id=plan_id, produkt=produkt, sekcja=sekcja, typ=typ)


@warehouse_bp.route('/edytuj_palete_page/<int:paleta_id>', methods=['GET'])
@login_required
def edytuj_palete_page(paleta_id):
    """Render form for editing paleta weight"""
    conn = get_db_connection()
    cursor = conn.cursor()
    waga = None
    sekcja = None
    try:
        cursor.execute("SELECT waga, plan_id FROM palety_workowanie WHERE id=%s", (paleta_id,))
        row = cursor.fetchone()
        if row:
            waga = row[0]
            plan_id = row[1]
            cursor.execute("SELECT sekcja FROM plan_produkcji WHERE id=%s", (plan_id,))
            r2 = cursor.fetchone()
            if r2:
                sekcja = r2[0]
    except Exception:
        try: current_app.logger.exception('Failed to load paleta %s for edit page', paleta_id)
        except Exception: pass
    finally:
        try: conn.close()
        except Exception: pass
    return render_template('edytuj_palete_popup.html', paleta_id=paleta_id, waga=waga, sekcja=sekcja)


@warehouse_bp.route('/confirm_delete_palete_page/<int:paleta_id>', methods=['GET'])
@login_required
def confirm_delete_palete_page(paleta_id):
    """Render delete confirmation for paleta"""
    return render_template('confirm_delete_palete.html', paleta_id=paleta_id)


@warehouse_bp.route('/confirm_delete_szarze_page/<int:szarza_id>', methods=['GET'])
@login_required
def confirm_delete_szarze_page(szarza_id):
    """Render delete confirmation for szarża"""
    return render_template('confirm_delete_szarze.html', szarza_id=szarza_id)


@warehouse_bp.route('/potwierdz_palete_page/<int:paleta_id>', methods=['GET'])
@login_required
def potwierdz_palete_page(paleta_id):
    """Render form for confirming paleta acceptance"""
    conn = get_db_connection()
    cursor = conn.cursor()
    waga = None
    try:
        cursor.execute("SELECT waga, waga_brutto, tara FROM palety_workowanie WHERE id=%s", (paleta_id,))
        row = cursor.fetchone()
        if row:
            waga = row[0]
    except Exception:
        try: current_app.logger.exception('Failed to load paleta %s for potwierdz_palete_page', paleta_id)
        except Exception: pass
    finally:
        try: conn.close()
        except Exception: pass
    return render_template('potwierdz_palete.html', paleta_id=paleta_id, waga=waga)


@warehouse_bp.route('/potwierdz_palete/<int:paleta_id>', methods=['POST'])
@login_required
def potwierdz_palete(paleta_id):
    """Confirm paleta acceptance with warehouse manager/lider"""
    role = session.get('rola', '')
    if role not in ['magazynier', 'lider', 'admin']:
        return ("Brak uprawnień", 403)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        try:
            cursor.execute("ALTER TABLE palety_workowanie ADD COLUMN status VARCHAR(32) DEFAULT 'do_przyjecia'")
            conn.commit()
        except Exception:
            try: conn.rollback()
            except Exception: pass

        try:
            cursor.execute("SELECT COALESCE(tara,25) FROM palety_workowanie WHERE id=%s", (paleta_id,))
            trow = cursor.fetchone()
            tara = int(trow[0]) if trow and trow[0] is not None else 25
        except Exception:
            tara = 25

        try:
            if request.form.get('waga_palety'):
                try:
                    waga_input = int(float(require_field(request.form, 'waga_palety').replace(',', '.')))
                except Exception:
                    waga_input = None
                if waga_input is not None:
                    cursor.execute("UPDATE palety_workowanie SET waga=%s WHERE id=%s", (waga_input, paleta_id))
                    conn.commit()
            elif request.form.get('waga_brutto'):
                try:
                    brutto = int(float(require_field(request.form, 'waga_brutto').replace(',', '.')))
                except Exception:
                    brutto = 0
                netto = brutto - int(tara)
                if netto < 0: netto = 0
                cursor.execute("UPDATE palety_workowanie SET waga_brutto=%s, waga=%s WHERE id=%s", (brutto, netto, paleta_id))
                conn.commit()
        except Exception:
            try: current_app.logger.exception('Failed to set weight for id=%s', paleta_id)
            except Exception: pass

        try:
            from datetime import datetime as _dt
            current_time = _dt.now().time()
            cursor.execute("UPDATE palety_workowanie SET status='przyjeta', data_potwierdzenia=NOW(), czas_potwierdzenia_s = TIMESTAMPDIFF(SECOND, data_dodania, NOW()), czas_rzeczywistego_potwierdzenia=%s WHERE id=%s", (current_time, paleta_id))
            conn.commit()
        except Exception:
            try:
                cursor.execute("UPDATE palety_workowanie SET status='przyjeta' WHERE id=%s", (paleta_id,))
                conn.commit()
            except Exception:
                try: conn.rollback()
                except Exception: pass

        try:
            cursor.execute("SELECT id, COALESCE(status,''), data_potwierdzenia, czas_potwierdzenia_s FROM palety_workowanie WHERE id=%s", (paleta_id,))
            res = cursor.fetchone()
            current_app.logger.info('potwierdz_palete result: %s', res)
        except Exception:
            try:
                current_app.logger.exception('Failed to fetch result for id=%s', paleta_id)
            except Exception: pass

        try:
            cursor.execute("SELECT plan_id, COALESCE(waga,0) FROM palety_workowanie WHERE id=%s", (paleta_id,))
            r = cursor.fetchone()
            if r:
                plan_id = r[0]
                netto_val = int(r[1] or 0)
                try:
                    cursor.execute("UPDATE plan_produkcji SET tonaz_rzeczywisty = (SELECT COALESCE(SUM(waga), 0) FROM palety_workowanie WHERE plan_id = %s AND status != 'przyjeta') WHERE id = %s", (plan_id, plan_id))
                except Exception:
                    try: conn.rollback()
                    except Exception: pass
                try:
                    cursor.execute("SELECT data_planu, produkt FROM plan_produkcji WHERE id=%s", (plan_id,))
                    z = cursor.fetchone()
                    if z:
                        cursor.execute("UPDATE plan_produkcji SET tonaz_rzeczywisty = tonaz_rzeczywisty + %s WHERE data_planu=%s AND produkt=%s AND sekcja='Magazyn'", (netto_val, z[0], z[1]))
                except Exception:
                    try: conn.rollback()
                    except Exception: pass
                conn.commit()
        except Exception:
            try:
                current_app.logger.exception('Failed to update plan aggregates for %s', paleta_id)
            except Exception: pass
    except Exception:
        current_app.logger.exception('Failed to potwierdz palete %s', paleta_id)
    finally:
        try: conn.close()
        except Exception: pass

    try:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return ('', 204)
    except Exception:
        pass
    return redirect(bezpieczny_powrot())


# DEBUG: no-auth route to reproduce template rendering issues (do not expose in production)
@warehouse_bp.route('/debug/noauth/dodaj_palete_page/<int:plan_id>', methods=['GET'])
def dodaj_palete_page_noauth(plan_id):
    """Debug helper: render `dodaj_palete_popup.html` without login decorator.
    Use to reproduce TemplateNotFound or rendering errors in a controlled way.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    produkt = None
    sekcja = None
    typ = None
    try:
        cursor.execute("SELECT produkt, sekcja, typ_produkcji FROM plan_produkcji WHERE id=%s", (plan_id,))
        row = cursor.fetchone()
        if row:
            produkt, sekcja, typ = row[0], row[1], row[2]
    except Exception:
        try:
            current_app.logger.exception('Failed to fetch plan %s for debug dodaj_palete_page', plan_id)
        except Exception:
            pass
    finally:
        try:
            conn.close()
        except Exception:
            pass

    try:
        return render_template('dodaj_palete_popup.html', plan_id=plan_id, produkt=produkt, sekcja=sekcja, typ=typ)
    except Exception as e:
        try:
            current_app.logger.exception('Debug render_template failed for plan %s: %s', plan_id, e)
        except Exception:
            pass
        # Return the error detail to caller for quick debugging (safe in local dev)
        return (f'Debug render error: {type(e).__name__}: {str(e)}', 500)


@warehouse_bp.route('/api/bufor', methods=['GET'])
def api_bufor():
    """Public API returning bufor entries as JSON (czyta z tabeli bufor z systemem kolejkowania)"""
    from datetime import date as _date
    from app.db import refresh_bufor_queue
    
    out = []
    qdate = request.args.get('data') or str(_date.today())
    
    try:
        # Odśwież bufor przed zwróceniem danych
        refresh_bufor_queue()
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Pobierz wszystkie wpisy z bufora dla danego dnia, posortowane po kolejce
        cur.execute("""
            SELECT id, zasyp_id, data_planu, produkt, nazwa_zlecenia, typ_produkcji, 
                   tonaz_rzeczywisty, spakowano, kolejka
            FROM bufor
            WHERE data_planu = %s AND status = 'aktywny'
            ORDER BY kolejka ASC
        """, (qdate,))
        
        rows = cur.fetchall()
        
        for row in rows:
            buf_id, z_id, z_data, z_produkt, z_nazwa, z_typ, z_tonaz, z_spakowano, z_kolejka = row
            
            pozostalo_w_silosie = max(z_tonaz - z_spakowano, 0)
            needs_reconciliation = round((z_spakowano or 0) - (z_tonaz or 0), 1) != 0
            show_in_bufor = (pozostalo_w_silosie > 0) or (z_spakowano and z_spakowano > 0)
            
            if show_in_bufor:
                out.append({
                    'id': z_id,
                    'data': str(z_data),
                    'produkt': z_produkt,
                    'nazwa': z_nazwa,
                    'w_silosie': round(max(pozostalo_w_silosie, 0), 1),
                    'typ_produkcji': z_typ,
                    'zasyp_total': z_tonaz,
                    'spakowano_total': z_spakowano,
                    'kolejka': z_kolejka,
                    'needs_reconciliation': needs_reconciliation,
                    'raw_pozostalo': round(pozostalo_w_silosie, 1)
                })
        
        conn.close()
        
    except Exception as e:
        try: 
            import traceback
            print(f"[ERROR] api_bufor: {e}")
            traceback.print_exc()
            conn.close()
        except Exception: 
            pass
        return jsonify({'bufor': [], 'error': True, 'message': str(e)}), 500

    return jsonify({'bufor': out})


@warehouse_bp.route('/bufor', methods=['GET'])
@login_required
@roles_required('planista', 'zarzad', 'lider', 'admin', 'laboratorium')
def bufor_page_html():
    """HTML page for buffer management with 'Create Order' buttons"""
    from datetime import date as _date
    from app.db import refresh_bufor_queue
    
    wybrana_data = request.args.get('data', str(_date.today()))
    bufor_list = []
    
    try:
        # Refresh buffer before displaying
        refresh_bufor_queue()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Read buffer entries for selected date
        cursor.execute("""
            SELECT b.id, b.zasyp_id, b.data_planu, b.produkt, b.nazwa_zlecenia, 
                   b.typ_produkcji, b.tonaz_rzeczywisty, b.spakowano, b.kolejka,
                   z.real_start, z.status
            FROM bufor b
            LEFT JOIN plan_produkcji z ON z.id = b.zasyp_id
            WHERE b.data_planu = %s AND b.status = 'aktywny'
            ORDER BY b.kolejka ASC
        """, (wybrana_data,))
        
        rows = cursor.fetchall()
        
        for row in rows:
            (buf_id, z_id, z_data, z_produkt, z_nazwa, z_typ, z_tonaz, z_spakowano, 
             z_kolejka, z_real_start, z_status) = row
            
            pozostalo_w_silosie = (z_tonaz or 0) - (z_spakowano or 0)
            needs_reconciliation = round((z_spakowano or 0) - (z_tonaz or 0), 1) != 0
            start_time = z_real_start.strftime('%H:%M') if z_real_start else 'N/A'
            
            bufor_list.append({
                'id': z_id,
                'data': str(z_data),
                'produkt': z_produkt,
                'nazwa': z_nazwa or '',
                'w_silosie': round(max(pozostalo_w_silosie, 0), 1),
                'typ_produkcji': z_typ or '',
                'zasyp_total': z_tonaz or 0,
                'spakowano_total': z_spakowano or 0,
                'kolejka': z_kolejka,
                'needs_reconciliation': needs_reconciliation,
                'raw_pozostalo': round(pozostalo_w_silosie, 1),
                'status': z_status or 'zaplanowane',
                'real_start': z_real_start,
                'start_time': start_time
            })
        
        conn.close()
        
    except Exception as e:
        current_app.logger.error(f"ERROR in bufor_page_html for date {wybrana_data}: {type(e).__name__}: {str(e)}", exc_info=True)
        bufor_list = []
    
    return render_template('bufor.html', bufor_list=bufor_list, wybrana_data=wybrana_data)


@warehouse_bp.route('/bufor/create_zlecenie', methods=['POST'])
@login_required
@roles_required('planista', 'admin', 'zarzad', 'lider')
def warehouse_bufor_create_zlecenie():
    """Create new Workowanie zlecenie based on buffer remainder (Zasyp.tonaz_rzeczywisty - spakowano)."""
    try:
        data = request.get_json(force=True) if request.is_json else request.form.to_dict()
    except Exception:
        data = request.form.to_dict()
    
    zasyp_id = data.get('zasyp_id')
    if not zasyp_id:
        return jsonify({'success': False, 'message': 'Brak zasyp_id'}), 400
    
    try:
        zasyp_id = int(zasyp_id)
    except Exception:
        return jsonify({'success': False, 'message': 'Nieprawidłowy zasyp_id'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Get Zasyp details (tonaz_rzeczywisty, date, product, type)
        cursor.execute("""
            SELECT id, data_planu, produkt, tonaz_rzeczywisty, typ_produkcji, nazwa_zlecenia
            FROM plan_produkcji
            WHERE id = %s AND sekcja = 'Zasyp'
        """, (zasyp_id,))
        zasyp = cursor.fetchone()
        
        if not zasyp:
            conn.close()
            return jsonify({'success': False, 'message': 'Nie znaleziono Zasypu'}), 404
        
        z_id, z_data, z_produkt, z_tonaz_rz, z_typ, z_nazwa = zasyp
        
        # Get how much was already packed (sum from bufor.spakowano)
        cursor.execute("""
            SELECT SUM(spakowano) FROM bufor
            WHERE zasyp_id = %s AND data_planu = %s AND status = 'aktywny'
        """, (zasyp_id, z_data))
        
        result = cursor.fetchone()
        spakowano = result[0] or 0 if result else 0
        
        # Calculate remainder: Zasyp.tonaz_rzeczywisty - spakowano
        roznicza = (z_tonaz_rz or 0) - spakowano
        
        if roznicza <= 0:
            conn.close()
            return jsonify({'success': False, 'message': 'Nie ma pozostałego towaru do spakowania (różnica <= 0)'}), 400
        
        # Get next sequence number for Workowanie section
        cursor.execute("""
            SELECT MAX(kolejnosc) FROM plan_produkcji 
            WHERE data_planu = %s AND sekcja = 'Workowanie'
        """, (z_data,))
        
        result = cursor.fetchone()
        next_kolejnosc = (result[0] or 0) + 1 if result else 1
        
        # Create new Workowanie zlecenie with plan = roznicza
        cursor.execute("""
            INSERT INTO plan_produkcji 
            (data_planu, sekcja, produkt, tonaz, status, kolejnosc, typ_produkcji, nazwa_zlecenia)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            z_data,
            'Workowanie',
            z_produkt,
            round(roznicza, 1),  # plan = różnica
            'zaplanowane',
            next_kolejnosc,
            z_typ or 'worki_zgrzewane_25',
            (z_nazwa or '') + '_BUF'  # Add _BUF suffix to mark buffer origin
        ))
        
        conn.commit()
        new_id = cursor.lastrowid
        
        conn.close()
        return jsonify({
            'success': True,
            'message': f'Utworzono zlecenie Workowanie z planem {round(roznicza, 1)} kg',
            'new_id': new_id,
            'plan_kg': round(roznicza, 1)
        }), 201
        
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        current_app.logger.exception('Error in warehouse_bufor_create_zlecenie')
        return jsonify({'success': False, 'message': f'Błąd: {str(e)}'}), 500
    finally:
        try:
            conn.close()
        except Exception:
            pass


@warehouse_bp.route('/api/start_from_queue/<int:kolejka>', methods=['POST'])
@login_required
def start_from_queue(kolejka):
    """Startu zlecenie z bufora po numerze kolejki"""
    from datetime import datetime as _datetime
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Pobierz wpis z bufora po kolejce
        cur.execute("""
            SELECT b.zasyp_id, b.data_planu, b.produkt, b.kolejka,
                   w.id as workowanie_id
            FROM bufor b
            LEFT JOIN plan_produkcji w ON w.produkt = b.produkt 
                AND w.data_planu = b.data_planu 
                AND w.sekcja = 'Workowanie'
            WHERE b.kolejka = %s AND b.status = 'aktywny'
            LIMIT 1
        """, (kolejka,))
        
        row = cur.fetchone()
        
        if not row:
            return jsonify({'success': False, 'message': f'Nie znaleziono wpisu w bufore z kolejką {kolejka}'}), 404
        
        zasyp_id, data_planu, produkt, buf_kolejka, workowanie_id = row
        
        if not workowanie_id:
            return jsonify({'success': False, 'message': f'Brak odpowiadającego Workowania dla {produkt} na dzień {data_planu}'}), 400
        
        # Zaktualizuj status Workowania na 'w toku' i ustaw real_start
        cur.execute("""
            UPDATE plan_produkcji 
            SET status = 'w toku', real_start = %s
            WHERE id = %s AND sekcja = 'Workowanie'
        """, (_datetime.now(), workowanie_id))
        
        # Oznacz ten wpis bufora jako 'startowany'
        cur.execute("""
            UPDATE bufor 
            SET status = 'startowany'
            WHERE kolejka = %s AND status = 'aktywny'
        """, (kolejka,))
        
        conn.commit()
        
        return jsonify({
            'success': True,
            'message': f'Uruchomiono zlecenie {produkt} (kolejka {buf_kolejka})',
            'workowanie_id': workowanie_id,
            'produkt': produkt,
            'kolejka': buf_kolejka
        }), 200
    
    except Exception as e:
        conn.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500
    
    finally:
        try: cur.close()
        except Exception: pass
        try: conn.close()
        except Exception: pass


@warehouse_bp.route('/wazenie_magazyn/<int:paleta_id>', methods=['POST'])
@login_required
def wazenie_magazyn(paleta_id):
    """Weigh paleta in warehouse and update weight"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        brutto = int(float(request.form.get('waga_brutto', '0').replace(',', '.')))
    except Exception:
        brutto = 0
    
    cursor.execute("SELECT tara, plan_id FROM palety_workowanie WHERE id=%s", (paleta_id,))
    res = cursor.fetchone()
    if res:
        tara, plan_id = res
        netto = brutto - int(tara)
        if netto < 0: netto = 0
        cursor.execute("UPDATE palety_workowanie SET waga_brutto=%s, waga=%s WHERE id=%s", (brutto, netto, paleta_id))
        cursor.execute("UPDATE plan_produkcji SET tonaz_rzeczywisty = (SELECT COALESCE(SUM(waga), 0) FROM palety_workowanie WHERE plan_id = %s AND status != 'przyjeta') WHERE id = %s", (plan_id, plan_id))
        cursor.execute("SELECT data_planu, produkt FROM plan_produkcji WHERE id=%s", (plan_id,))
        z = cursor.fetchone()
        if z: 
            cursor.execute("UPDATE plan_produkcji SET tonaz_rzeczywisty = tonaz_rzeczywisty + %s WHERE data_planu=%s AND produkt=%s AND sekcja='Magazyn'", (netto, z[0], z[1]))
    
    conn.commit()
    conn.close()
    return redirect(bezpieczny_powrot())


@warehouse_bp.route('/usun_szarze/<int:id>', methods=['POST'])
@roles_required('lider', 'admin')
def usun_szarze(id):
    """Delete szarża from Zasyp section"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT plan_id FROM szarze WHERE id=%s", (id,))
        res = cursor.fetchone()
        if res:
            plan_id = res[0]
            cursor.execute("DELETE FROM szarze WHERE id=%s", (id,))
            cursor.execute("UPDATE plan_produkcji SET tonaz_rzeczywisty = COALESCE((SELECT SUM(waga) FROM szarze WHERE plan_id = %s), 0) WHERE id = %s", (plan_id, plan_id))
            conn.commit()
    finally:
        conn.close()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'message': 'Szarża usunięta'}), 200
    
    return redirect(bezpieczny_powrot())


@warehouse_bp.route('/usun_palete/<int:id>', methods=['POST'])
@roles_required('lider', 'admin')
def usun_palete(id):
    """Delete paleta from buffer"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT plan_id FROM palety_workowanie WHERE id=%s", (id,))
        res = cursor.fetchone()
        if res:
            plan_id = res[0]
            cursor.execute("DELETE FROM palety_workowanie WHERE id=%s", (id,))
            cursor.execute("UPDATE plan_produkcji SET tonaz_rzeczywisty = (SELECT COALESCE(SUM(waga), 0) FROM palety_workowanie WHERE plan_id = %s AND status != 'przyjeta') WHERE id = %s", (plan_id, plan_id))
            conn.commit()
    finally:
        conn.close()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'message': 'Paleta usunięta'}), 200
    
    return redirect(bezpieczny_powrot())


@warehouse_bp.route('/edytuj_palete/<int:paleta_id>', methods=['POST'])
@roles_required('lider', 'admin')
def edytuj_palete(paleta_id):
    """Edit paleta weight (netto)"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            waga = int(float(request.form.get('waga_palety', '0').replace(',', '.')))
        except Exception:
            waga = 0
        
        cursor.execute("UPDATE palety_workowanie SET waga=%s WHERE id=%s", (waga, paleta_id))
        cursor.execute("SELECT plan_id FROM palety_workowanie WHERE id=%s", (paleta_id,))
        res = cursor.fetchone()
        if res:
            plan_id = res[0]
            cursor.execute("UPDATE plan_produkcji SET tonaz_rzeczywisty = (SELECT COALESCE(SUM(waga), 0) FROM palety_workowanie WHERE plan_id = %s AND status != 'przyjeta') WHERE id = %s", (plan_id, plan_id))
        conn.commit()
    except Exception:
        current_app.logger.exception('Failed to edit paleta %s', paleta_id)
    finally:
        try: conn.close()
        except Exception: pass
    
    return redirect(bezpieczny_powrot())


