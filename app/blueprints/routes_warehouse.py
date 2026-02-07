from flask import Blueprint, request, redirect, url_for, flash, session, render_template, current_app, jsonify
from datetime import date, datetime
from app.db import get_db_connection
from app.decorators import login_required, roles_required
from utils.validation import require_field

warehouse_bp = Blueprint('warehouse', __name__)

def bezpieczny_powrot():
    """Default return path: planner view or dashboard"""
    if session.get('rola') == 'planista' or request.form.get('widok_powrotu') == 'planista':
        data = request.form.get('data_powrotu') or request.args.get('data') or str(date.today())
        return url_for('planista.panel_planisty', data=data)
    
    sekcja = request.args.get('sekcja') or request.form.get('sekcja', 'Zasyp')
    data = request.form.get('data_powrotu') or request.args.get('data') or str(date.today())
    return url_for('index', sekcja=sekcja, data=data)


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
            "UPDATE plan_produkcji SET tonaz_rzeczywisty = COALESCE(tonaz_rzeczywisty, 0) - %s WHERE id = %s",
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


@warehouse_bp.route('/bufor', methods=['GET'])
def api_bufor():
    """Public API returning bufor entries as JSON"""
    from datetime import date as _date
    out = []
    qdate = request.args.get('data') or str(_date.today())
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT id, data_planu, produkt, tonaz_rzeczywisty, nazwa_zlecenia, typ_produkcji
            FROM plan_produkcji
            WHERE sekcja = 'Zasyp'
              AND data_planu >= DATE_SUB(%s, INTERVAL 7 DAY)
              AND data_planu <= %s
        """, (qdate, qdate))
        rows = cur.fetchall()
        for hz in rows:
            h_id, h_data, h_produkt, h_wykonanie_zasyp, h_nazwa, h_typ = hz
            typ_param = h_typ if h_typ is not None else ''
            cur.execute(
                "SELECT SUM(waga) FROM palety_workowanie WHERE plan_id = %s OR plan_id IN (SELECT id FROM plan_produkcji WHERE data_planu=%s AND produkt=%s AND sekcja='Workowanie' AND COALESCE(typ_produkcji,'')=%s)",
                (h_id, h_data, h_produkt, typ_param)
            )
            res_pal = cur.fetchone()
            h_wykonanie_workowanie = res_pal[0] if res_pal and res_pal[0] else 0
            pozostalo_w_silosie = (h_wykonanie_zasyp or 0) - (h_wykonanie_workowanie or 0)
            needs_reconciliation = round((h_wykonanie_workowanie or 0) - (h_wykonanie_zasyp or 0), 1) != 0
            show_in_bufor = (pozostalo_w_silosie > 0) or (h_wykonanie_workowanie and h_wykonanie_workowanie > 0)
            if show_in_bufor:
                out.append({
                    'id': h_id,
                    'data': str(h_data),
                    'produkt': h_produkt,
                    'nazwa': h_nazwa,
                    'w_silosie': round(max(pozostalo_w_silosie, 0), 1),
                    'typ_produkcji': h_typ,
                    'zasyp_total': h_wykonanie_zasyp,
                    'spakowano_total': h_wykonanie_workowanie,
                    'needs_reconciliation': needs_reconciliation,
                    'raw_pozostalo': round(pozostalo_w_silosie, 1)
                })
    except Exception:
        try: conn.close()
        except Exception: pass
        return jsonify({'bufor': [], 'error': True}), 500
    finally:
        try: conn.close()
        except Exception: pass

    return jsonify({'bufor': out})


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


