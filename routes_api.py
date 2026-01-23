from flask import Blueprint, request, redirect, url_for, flash, session, render_template
from datetime import date, datetime, timedelta, time
from db import get_db_connection
from decorators import login_required

api_bp = Blueprint('api', __name__)

def bezpieczny_powrot():
    """Wraca do Planisty jeśli to on klikał, w przeciwnym razie na Dashboard"""
    if session.get('rola') == 'planista' or request.form.get('widok_powrotu') == 'planista':
        data = request.form.get('data_powrotu') or request.args.get('data') or str(date.today())
        return url_for('planista.panel_planisty', data=data)
    
    sekcja = request.form.get('sekcja', 'Zasyp')
    data = request.form.get('data_powrotu') or str(date.today())
    return url_for('index', sekcja=sekcja, data=data)

# ================= PRODUKCJA =================

@api_bp.route('/start_zlecenie/<int:id>', methods=['POST'])
@login_required
def start_zlecenie(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT produkt, tonaz, sekcja, data_planu, typ_produkcji, status FROM plan_produkcji WHERE id=%s", (id,))
    z = cursor.fetchone()
    
    if z:
        produkt, tonaz, sekcja, data_planu, typ, status_obecny = z
        if status_obecny != 'w toku':
            cursor.execute("UPDATE plan_produkcji SET status='zaplanowane', real_stop=NULL WHERE sekcja=%s AND status='w toku'", (sekcja,))
            cursor.execute("UPDATE plan_produkcji SET status='w toku', real_start=NOW(), real_stop=NULL WHERE id=%s", (id,))
        
        if sekcja == 'Zasyp' and status_obecny == 'zaplanowane':
            cursor.execute("SELECT id FROM plan_produkcji WHERE data_planu=%s AND produkt=%s AND sekcja='Workowanie' AND typ_produkcji=%s", (data_planu, produkt, typ))
            istniejace = cursor.fetchone()
            if not istniejace:
                cursor.execute("SELECT MAX(kolejnosc) FROM plan_produkcji WHERE data_planu=%s", (data_planu,))
                res = cursor.fetchone(); mk = res[0] if res and res[0] else 0; nk = mk + 1
                cursor.execute("INSERT INTO plan_produkcji (data_planu, sekcja, produkt, tonaz, status, kolejnosc, typ_produkcji) VALUES (%s, 'Workowanie', %s, %s, 'zaplanowane', %s, %s)", (data_planu, produkt, tonaz, nk, typ))
            else:
                cursor.execute("UPDATE plan_produkcji SET tonaz=%s WHERE id=%s", (tonaz, istniejace[0]))
    conn.commit(); conn.close(); return redirect(bezpieczny_powrot())

@api_bp.route('/koniec_zlecenie/<int:id>', methods=['POST'])
@login_required
def koniec_zlecenie(id):
    conn = get_db_connection(); cursor = conn.cursor()
    final_tonaz = request.form.get('final_tonaz'); wyjasnienie = request.form.get('wyjasnienie')
    rzeczywista_waga = 0
    if final_tonaz:
        try: rzeczywista_waga = int(float(final_tonaz.replace(',', '.')))
        except: pass

    sql = "UPDATE plan_produkcji SET status='zakonczone', real_stop=NOW()"; params = []
    if rzeczywista_waga > 0: sql += ", tonaz_rzeczywisty=%s"; params.append(rzeczywista_waga)
    if wyjasnienie: sql += ", wyjasnienie_rozbieznosci=%s"; params.append(wyjasnienie)
    sql += " WHERE id=%s"; params.append(id); cursor.execute(sql, tuple(params))
    
    cursor.execute("SELECT sekcja, produkt, data_planu, tonaz FROM plan_produkcji WHERE id=%s", (id,)); z = cursor.fetchone()
    if z and z[0] == 'Zasyp' and rzeczywista_waga > 0:
        cursor.execute("UPDATE plan_produkcji SET tonaz=%s WHERE data_planu=%s AND produkt=%s AND tonaz=%s AND sekcja='Workowanie' AND status != 'zakonczone' LIMIT 1", (rzeczywista_waga, z[2], z[1], z[3]))
    conn.commit(); conn.close(); return redirect(bezpieczny_powrot())

@api_bp.route('/zapisz_wyjasnienie/<int:id>', methods=['POST'])
@login_required
def zapisz_wyjasnienie(id):
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("UPDATE plan_produkcji SET wyjasnienie_rozbieznosci=%s WHERE id=%s", (request.form.get('wyjasnienie'), id))
    conn.commit(); conn.close(); return redirect(bezpieczny_powrot())

# ================= PALETY =================

@api_bp.route('/dodaj_palete/<int:plan_id>', methods=['POST'])
@login_required
def dodaj_palete(plan_id):
    conn = get_db_connection(); cursor = conn.cursor()
    try: waga_input = int(float(request.form.get('waga_palety', '0').replace(',', '.')))
    except: waga_input = 0
    typ = request.form.get('typ_produkcji', 'standard')
    
    if typ == 'bigbag': cursor.execute("INSERT INTO palety_workowanie (plan_id, waga, tara, waga_brutto) VALUES (%s, 0, %s, 0)", (plan_id, waga_input))
    else: cursor.execute("INSERT INTO palety_workowanie (plan_id, waga, tara, waga_brutto) VALUES (%s, %s, 25, 0)", (plan_id, waga_input))
    
    cursor.execute("UPDATE plan_produkcji SET tonaz_rzeczywisty = (SELECT COALESCE(SUM(waga), 0) FROM palety_workowanie WHERE plan_id = %s) WHERE id = %s", (plan_id, plan_id))
    cursor.execute("SELECT data_planu, produkt, tonaz, typ_produkcji FROM plan_produkcji WHERE id=%s", (plan_id,)); z = cursor.fetchone()
    if z:
        cursor.execute("SELECT id FROM plan_produkcji WHERE data_planu=%s AND produkt=%s AND sekcja='Magazyn' AND typ_produkcji=%s AND status != 'zakonczone' LIMIT 1", (z[0], z[1], z[3]))
        istniejace = cursor.fetchone()
        if not istniejace: cursor.execute("INSERT INTO plan_produkcji (data_planu, sekcja, produkt, tonaz, status, kolejnosc, typ_produkcji) VALUES (%s, 'Magazyn', %s, %s, 'zaplanowane', 999, %s)", (z[0], z[1], z[2], z[3]))
        else: cursor.execute("UPDATE plan_produkcji SET tonaz=%s WHERE id=%s", (z[2], istniejace[0]))
    conn.commit(); conn.close(); return redirect(bezpieczny_powrot())

@api_bp.route('/wazenie_magazyn/<int:paleta_id>', methods=['POST'])
@login_required
def wazenie_magazyn(paleta_id):
    conn = get_db_connection(); cursor = conn.cursor()
    try: brutto = int(float(request.form.get('waga_brutto', '0').replace(',', '.')))
    except: brutto = 0
    cursor.execute("SELECT tara, plan_id FROM palety_workowanie WHERE id=%s", (paleta_id,)); res = cursor.fetchone()
    if res:
        tara, plan_id = res; netto = brutto - int(tara)
        if netto < 0: netto = 0
        cursor.execute("UPDATE palety_workowanie SET waga_brutto=%s, waga=%s WHERE id=%s", (brutto, netto, paleta_id))
        cursor.execute("UPDATE plan_produkcji SET tonaz_rzeczywisty = (SELECT COALESCE(SUM(waga), 0) FROM palety_workowanie WHERE plan_id = %s) WHERE id = %s", (plan_id, plan_id))
        cursor.execute("SELECT data_planu, produkt FROM plan_produkcji WHERE id=%s", (plan_id,)); z = cursor.fetchone()
        if z: cursor.execute("UPDATE plan_produkcji SET tonaz_rzeczywisty = tonaz_rzeczywisty + %s WHERE data_planu=%s AND produkt=%s AND sekcja='Magazyn'", (netto, z[0], z[1]))
    conn.commit(); conn.close(); return redirect(bezpieczny_powrot())

@api_bp.route('/usun_palete/<int:id>', methods=['POST'])
@login_required
def usun_palete(id):
    if session.get('rola') not in ['lider', 'admin']: return redirect(bezpieczny_powrot())
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("SELECT plan_id FROM palety_workowanie WHERE id=%s", (id,)); res = cursor.fetchone()
    if res:
        plan_id = res[0]; cursor.execute("DELETE FROM palety_workowanie WHERE id=%s", (id,))
        cursor.execute("UPDATE plan_produkcji SET tonaz_rzeczywisty = (SELECT COALESCE(SUM(waga), 0) FROM palety_workowanie WHERE plan_id = %s) WHERE id = %s", (plan_id, plan_id))
        conn.commit()
    conn.close(); return redirect(bezpieczny_powrot())

# ================= ZARZĄDZANIE (ZABEZPIECZONE) =================

@api_bp.route('/przywroc_zlecenie/<int:id>', methods=['POST'])
@login_required
def przywroc_zlecenie(id):
    if session.get('rola') not in ['lider', 'admin']: return redirect('/')
    conn = get_db_connection(); cursor = conn.cursor(); cursor.execute("SELECT sekcja FROM plan_produkcji WHERE id=%s", (id,)); res = cursor.fetchone()
    if res: cursor.execute("UPDATE plan_produkcji SET status='zaplanowane', real_stop=NULL WHERE sekcja=%s AND status='w toku'", (res[0],)); cursor.execute("UPDATE plan_produkcji SET status='w toku', real_stop=NULL WHERE id=%s", (id,)); conn.commit()
    conn.close(); return redirect(bezpieczny_powrot())

@api_bp.route('/zmien_status_zlecenia/<int:id>', methods=['POST'])
@login_required
def zmien_status_zlecenia(id): conn = get_db_connection(); cursor = conn.cursor(); cursor.execute("UPDATE plan_produkcji SET status=%s WHERE id=%s", (request.form.get('status'), id)); conn.commit(); conn.close(); return redirect(bezpieczny_powrot())

@api_bp.route('/usun_plan/<int:id>', methods=['POST'])
@login_required
def usun_plan(id):
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("SELECT status FROM plan_produkcji WHERE id=%s", (id,))
    res = cursor.fetchone()
    # BLOKADA: Nie usuwamy aktywnych
    if res and res[0] not in ['w toku', 'zakonczone']:
        cursor.execute("DELETE FROM plan_produkcji WHERE id=%s", (id,))
        conn.commit()
    conn.close()
    return redirect(bezpieczny_powrot())

@api_bp.route('/dodaj_plan_zaawansowany', methods=['POST'])
@login_required
def dodaj_plan_zaawansowany():
    if session.get('rola') not in ['planista', 'admin']: return redirect('/')
    sekcja = request.form.get('sekcja'); data_planu = request.form.get('data_planu'); produkt = request.form.get('produkt'); typ = request.form.get('typ_produkcji', 'standard'); status = 'nieoplacone' if request.form.get('wymaga_oplaty') else 'zaplanowane'
    try: tonaz = int(float(request.form.get('tonaz')))
    except: tonaz = 0
    conn = get_db_connection(); cursor = conn.cursor(); cursor.execute("SELECT MAX(kolejnosc) FROM plan_produkcji WHERE data_planu=%s", (data_planu,)); res = cursor.fetchone(); nk = (res[0] if res and res[0] else 0) + 1
    cursor.execute("INSERT INTO plan_produkcji (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji) VALUES (%s, %s, %s, %s, %s, %s, %s)", (data_planu, produkt, tonaz, status, sekcja, nk, typ))
    conn.commit(); conn.close(); return redirect(url_for('planista.panel_planisty', data=data_planu))

@api_bp.route('/przenies_zlecenie/<int:id>', methods=['POST'])
@login_required
def przenies_zlecenie(id):
    conn = get_db_connection(); cursor = conn.cursor()
    
    # BLOKADA: Sprawdź status przed zmianą daty
    cursor.execute("SELECT status FROM plan_produkcji WHERE id=%s", (id,))
    res = cursor.fetchone()
    if res and res[0] in ['w toku', 'zakonczone']:
        conn.close()
        return redirect(bezpieczny_powrot())

    nd = request.form.get('nowa_data')
    cursor.execute("SELECT MAX(kolejnosc) FROM plan_produkcji WHERE data_planu=%s", (nd,)); res = cursor.fetchone(); nk = (res[0] if res and res[0] else 0) + 1
    cursor.execute("UPDATE plan_produkcji SET data_planu=%s, kolejnosc=%s WHERE id=%s", (nd, nk, id))
    conn.commit(); conn.close(); return redirect(bezpieczny_powrot())

@api_bp.route('/przesun_zlecenie/<int:id>/<kierunek>', methods=['POST'])
@login_required
def przesun_zlecenie(id, kierunek):
    if session.get('rola') not in ['planista', 'admin']: return redirect('/')
    data = request.args.get('data', str(date.today())); conn = get_db_connection(); cursor = conn.cursor()
    
    # BLOKADA: Sprawdź status przed przesunięciem
    cursor.execute("SELECT id, kolejnosc, status FROM plan_produkcji WHERE id=%s", (id,))
    obecne = cursor.fetchone()
    
    if obecne and obecne[2] not in ['w toku', 'zakonczone']:
        oid, okol, _ = obecne
        q = "SELECT id, kolejnosc FROM plan_produkcji WHERE data_planu=%s AND kolejnosc < %s ORDER BY kolejnosc DESC LIMIT 1" if kierunek == 'gora' else "SELECT id, kolejnosc FROM plan_produkcji WHERE data_planu=%s AND kolejnosc > %s ORDER BY kolejnosc ASC LIMIT 1"
        cursor.execute(q, (data, okol)); sasiad = cursor.fetchone()
        if sasiad:
            cursor.execute("UPDATE plan_produkcji SET kolejnosc=%s WHERE id=%s", (sasiad[1], oid))
            cursor.execute("UPDATE plan_produkcji SET kolejnosc=%s WHERE id=%s", (okol, sasiad[0]))
            conn.commit()
            
    conn.close(); return redirect(url_for('planista.panel_planisty', data=data))

# ================= DZIENNIK =================

@api_bp.route('/dodaj_wpis', methods=['POST'])
@login_required
def dodaj_wpis(): conn = get_db_connection(); cursor = conn.cursor(); cursor.execute("INSERT INTO dziennik_zmiany (data_wpisu, sekcja, problem, czas_start, status, kategoria) VALUES (%s, %s, %s, %s, 'roboczy', %s)", (date.today(), request.form['sekcja'], request.form.get('problem'), request.form.get('czas_start'), request.form['kategoria'])); conn.commit(); conn.close(); return redirect(bezpieczny_powrot())

@api_bp.route('/usun_wpis/<int:id>', methods=['POST'])
@login_required
def usun_wpis(id): conn = get_db_connection(); cursor = conn.cursor(); cursor.execute("DELETE FROM dziennik_zmiany WHERE id=%s", (id,)); conn.commit(); conn.close(); return redirect(bezpieczny_powrot())

@api_bp.route('/edytuj/<int:id>', methods=['GET', 'POST'])
@login_required
def edytuj(id):
    conn = get_db_connection(); cursor = conn.cursor()
    try:
        if request.method == 'POST':
            cursor.execute("UPDATE dziennik_zmiany SET problem=%s, kategoria=%s, czas_start=%s, czas_stop=%s WHERE id=%s", (
                request.form.get('problem'), request.form.get('kategoria'), request.form.get('czas_start') or None, request.form.get('czas_stop') or None, id
            ))
            conn.commit(); conn.close();
            return redirect('/')

        cursor.execute("SELECT * FROM dziennik_zmiany WHERE id = %s", (id,)); wpis = cursor.fetchone()
        if not wpis:
            # brak wpisu — przyjazne przekierowanie
            conn.close()
            from flask import flash
            flash('Wpis nie został odnaleziony.', 'warning')
            return redirect(bezpieczny_powrot())

        # Format time fields for the template (HH:MM). db may return timedelta or datetime
        wpis_display = list(wpis)
        for ti in (6, 7):
            try:
                val = wpis[ti]
                if val is None:
                    wpis_display[ti] = ''
                elif isinstance(val, datetime):
                    wpis_display[ti] = val.strftime('%H:%M')
                elif isinstance(val, time):
                    wpis_display[ti] = val.strftime('%H:%M')
                elif isinstance(val, timedelta):
                    total_seconds = int(val.total_seconds())
                    h = total_seconds // 3600
                    m = (total_seconds % 3600) // 60
                    wpis_display[ti] = f"{h:02d}:{m:02d}"
                else:
                    # fallback to string, try to extract HH:MM
                    s = str(val)
                    if ':' in s:
                        parts = s.split(':')
                        wpis_display[ti] = f"{int(parts[0]):02d}:{int(parts[1]):02d}"
                    else:
                        wpis_display[ti] = s
            except Exception:
                wpis_display[ti] = ''

        conn.close()
        return render_template('edycja.html', wpis=wpis_display)
    except Exception:
        # Zaloguj i pokaż przyjazny komunikat zamiast 500
        app = None
        try:
            from flask import current_app
            app = current_app._get_current_object()
            app.logger.exception('Error in edytuj endpoint for id=%s', id)
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        from flask import flash
        flash('Wystąpił błąd podczas ładowania wpisu.', 'danger')
        return redirect(bezpieczny_powrot())


@api_bp.route('/ustawienia', methods=['GET'])
@login_required
def ustawienia():
    """Prosty widok ustawień (placeholder)."""
    try:
        return render_template('ustawienia.html')
    except Exception:
        from flask import flash
        flash('Nie można otworzyć strony ustawień.', 'danger')
        return redirect('/')

@api_bp.route('/zapisz_tonaz_deprecated/<int:id>', methods=['POST'])
def zapisz_tonaz_deprecated(id): return redirect(bezpieczny_powrot())

# ================= OBSADA I INNE =================
@api_bp.route('/dodaj_obecnosc', methods=['POST'])
@login_required
def dodaj_obecnosc(): conn = get_db_connection(); cursor = conn.cursor(); cursor.execute("INSERT INTO obecnosc (data_wpisu, pracownik_id, typ, ilosc_godzin, komentarz) VALUES (%s, %s, %s, %s, %s)", (date.today(), request.form['pracownik_id'], request.form['typ'], request.form.get('godziny', 0), request.form.get('komentarz'))); conn.commit(); conn.close(); return redirect(bezpieczny_powrot())

@api_bp.route('/usun_obecnosc/<int:id>', methods=['POST'])
@login_required
def usun_obecnosc(id): conn = get_db_connection(); cursor = conn.cursor(); cursor.execute("DELETE FROM obecnosc WHERE id=%s", (id,)); conn.commit(); conn.close(); return redirect(bezpieczny_powrot())

@api_bp.route('/dodaj_do_obsady', methods=['POST'])
@login_required
def dodaj_do_obsady(): conn = get_db_connection(); cursor = conn.cursor(); cursor.execute("INSERT INTO obsada_zmiany (data_wpisu, sekcja, pracownik_id) VALUES (%s, %s, %s)", (date.today(), request.form['sekcja'], request.form['pracownik_id'])); conn.commit(); conn.close(); return redirect(bezpieczny_powrot())

@api_bp.route('/usun_z_obsady/<int:id>', methods=['POST'])
@login_required
def usun_z_obsady(id): conn = get_db_connection(); cursor = conn.cursor(); cursor.execute("DELETE FROM obsada_zmiany WHERE id=%s", (id,)); conn.commit(); conn.close(); return redirect(bezpieczny_powrot())