from flask import Blueprint, render_template, request
from db import get_db_connection
from dto.paleta import PaletaDTO
from datetime import date
from decorators import roles_required

planista_bp = Blueprint('planista', __name__)

# --- KONFIGURACJA NORM (KG NA GODZINĘ) ---
# Tutaj możesz dostosować prędkość maszyny dla różnych typów opakowań
NORMY_KG_H = {
    'worki_zgrzewane_25': 3500,  # worki zgrzewane 25 kg
    'worki_zgrzewane_20': 3500,  # worki zgrzewane 20 kg (można dopasować)
    'worki_zszywane_25': 2500,   # worki zszywane 25 kg
    'worki_zszywane_20': 2500,   # worki zszywane 20 kg
    'bigbag': 5000,              # BigBag
}

@planista_bp.route('/planista', methods=['GET', 'POST'])
@roles_required('planista', 'zarzad', 'lider', 'admin', 'laboratorium')
def panel_planisty():

    conn = get_db_connection()
    cursor = conn.cursor()

    wybrana_data = request.args.get('data', str(date.today()))

    cursor.execute("""
        SELECT id, sekcja, produkt, tonaz, status, kolejnosc, real_start, real_stop, tonaz_rzeczywisty, typ_produkcji, wyjasnienie_rozbieznosci 
        FROM plan_produkcji 
        WHERE data_planu = %s AND sekcja = 'Zasyp'
        ORDER BY kolejnosc
    """, (wybrana_data,))
    
    plany = cursor.fetchall()
    plany_list = [list(p) for p in plany] # Lista edytowalna

    palety_mapa = {}
    suma_plan = 0
    suma_wyk = 0
    
    # NOWE ZMIENNE DO CZASU
    suma_minut_plan = 0 
    
    for p in plany_list:
        waga_plan = p[3] if p[3] else 0
        typ_prod = p[9]
        
        # 1. OBLICZANIE CZASU (Waga / Norma * 60 min)
        norma = NORMY_KG_H.get(typ_prod, 3000) # Domyślnie 3000 jeśli nieznany typ
        czas_trwania_min = int((waga_plan / norma) * 60)
        
        # Dodajemy obliczony czas do listy p (index 11)
        p.append(czas_trwania_min) 
        
        suma_plan += waga_plan
        suma_minut_plan += czas_trwania_min

        # 2. POBIERANIE WYKONANIA
        # Dla planów Zasyp: oblicz z szarży (rzeczywistych wpisów)
        # Dla planów innych sekcji: pobierz z planów Workowania/Magazynu
        plan_id = p[0]
        cursor.execute("SELECT SUM(waga) FROM szarze WHERE plan_id = %s", (plan_id,))
        szarze_result = cursor.fetchone()
        wykonanie_rzeczywiste = szarze_result[0] if szarze_result and szarze_result[0] else 0
        
        # Fallback: jeśli nie ma szarży, użyj tonaz_rzeczywisty z bazy
        if wykonanie_rzeczywiste == 0:
            wykonanie_rzeczywiste = p[8] if p[8] else 0
        
        p[8] = wykonanie_rzeczywiste
        suma_wyk += wykonanie_rzeczywiste

        # 3. POBIERANIE PALET
        cursor.execute("""
            SELECT pw.id, pw.plan_id, pw.waga, pw.tara, pw.waga_brutto, pw.data_dodania, pp.produkt, pp.typ_produkcji
            FROM palety_workowanie pw
            JOIN plan_produkcji pp ON pw.plan_id = pp.id
            WHERE pp.data_planu = %s AND pp.produkt = %s AND pp.typ_produkcji = %s AND pp.sekcja = 'Workowanie'
            ORDER BY pw.id DESC
        """, (wybrana_data, p[2], typ_prod))
        raw_pal = cursor.fetchall()
        formatted = []
        for r in raw_pal:
            dto = PaletaDTO.from_db_row(r)
            dt = dto.data_dodania
            try:
                sdt = dt.strftime('%H:%M') if hasattr(dt, 'strftime') else str(dt)
            except Exception:
                sdt = str(dt)
            formatted.append((dto.waga, sdt, dto.tara, dto.waga_brutto))
        palety_mapa[p[0]] = formatted

    conn.close()

    procent = (suma_wyk / suma_plan * 100) if suma_plan > 0 else 0
    
    # Obliczenie obłożenia zmiany (450 min to 7.5h pracy netto)
    procent_czasu = (suma_minut_plan / 450 * 100)

    # Pobierz zlecenia jakościowe zgłoszone na wybraną datę (laboratorium)
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, produkt, tonaz, sekcja, status FROM plan_produkcji WHERE data_planu=%s AND (COALESCE(typ_zlecenia, '') = 'jakosc' OR sekcja = 'Jakosc') AND status != 'zakonczone' ORDER BY id DESC", (wybrana_data,))
        quality_orders = cursor.fetchall()
        quality_count = len(quality_orders)
        conn.close()
    except Exception:
        quality_orders = []
        quality_count = 0

    return render_template('planista.html', 
                           plany=plany_list, 
                           wybrana_data=wybrana_data, 
                           palety_mapa=palety_mapa,
                           suma_plan=suma_plan,
                           suma_wyk=suma_wyk,
                           procent=procent,
                           suma_minut_plan=suma_minut_plan, # Przekazujemy sumę minut
                           procent_czasu=procent_czasu,     # Przekazujemy % zajętości zmiany
                           quality_count=quality_count,
                           quality_orders=quality_orders)


@planista_bp.route('/bufor', methods=['GET'])
@roles_required('planista', 'zarzad', 'lider', 'admin', 'laboratorium')
def bufor_page():
    conn = get_db_connection()
    cursor = conn.cursor()
    wybrana_data = request.args.get('data', str(date.today()))
    try:
        # Show all orders including closed ones - bufor stays open indefinitely
        cursor.execute("""
            SELECT id, data_planu, produkt, tonaz_rzeczywisty, nazwa_zlecenia, typ_produkcji, status, real_start
            FROM plan_produkcji
                        WHERE sekcja = 'Zasyp'
                            AND data_planu >= DATE_SUB(%s, INTERVAL 7 DAY)
                            AND data_planu <= %s
                        ORDER BY COALESCE(real_start, data_planu) DESC
        """, (wybrana_data, wybrana_data))
        historyczne_zasypy = cursor.fetchall()
        bufor_list = []
        for hz in historyczne_zasypy:
            h_id, h_data, h_produkt, h_wykonanie_zasyp, h_nazwa, h_typ, h_status, h_real_start = hz
            # Ensure typ_produkcji param is '' when DB value is NULL to match COALESCE in SQL
            typ_param = h_typ if h_typ is not None else ''
            # Sum palety zarówno bezpośrednio przypisane do zlecenia Zasyp (plan_id = h_id),
            # jak i te przypisane do odpowiadających zleceń Workowanie utworzonych z tego zasypu.
            cursor.execute(
                "SELECT SUM(waga) FROM palety_workowanie WHERE plan_id = %s OR plan_id IN ("
                "SELECT id FROM plan_produkcji WHERE data_planu=%s AND produkt=%s AND sekcja='Workowanie' AND COALESCE(typ_produkcji,'')=%s)",
                (h_id, h_data, h_produkt, typ_param)
            )
            res_pal = cursor.fetchone()
            h_wykonanie_workowanie = res_pal[0] if res_pal and res_pal[0] else 0
            pozostalo_w_silosie = (h_wykonanie_zasyp or 0) - (h_wykonanie_workowanie or 0)
            # Nowa logika prezentacji bufora:
            # - pokaż, jeśli w silosie zostało coś (>0)
            # - pokaż, jeśli workowanie już wystartowało (spakowano > 0),
            #   aby umożliwić weryfikację/rozliczenie (np. nadmiary/deficyty)
            show_in_bufor = (pozostalo_w_silosie > 0) or (h_wykonanie_workowanie and h_wykonanie_workowanie > 0)
            if show_in_bufor:
                needs_reconciliation = round((h_wykonanie_workowanie or 0) - (h_wykonanie_zasyp or 0), 1) != 0
                start_time = h_real_start.strftime('%H:%M') if h_real_start else 'N/A'
                bufor_list.append({
                    'id': h_id,
                    'data': h_data,
                    'produkt': h_produkt,
                    'nazwa': h_nazwa,
                    'w_silosie': round(max(pozostalo_w_silosie, 0), 1),
                    'typ_produkcji': h_typ,
                    'zasyp_total': h_wykonanie_zasyp,
                    'spakowano_total': h_wykonanie_workowanie,
                    'needs_reconciliation': needs_reconciliation,
                    'raw_pozostalo': round(pozostalo_w_silosie, 1),
                    'status': h_status,
                    'real_start': h_real_start,
                    'start_time': start_time
                })
    except Exception:
        bufor_list = []
    finally:
        conn.close()

    return render_template('bufor.html', bufor_list=bufor_list, wybrana_data=wybrana_data)


@planista_bp.route('/bufor/rozlicz', methods=['POST'])
@roles_required('planista', 'lider', 'admin')
def bufor_rozlicz():
    """Endpoint obsługujący rozliczenie zasypu: zapisuje `tonaz_rzeczywisty` i opcjonalnie zamyka zlecenie."""
    from flask import request, redirect
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        plan_id = int(request.form.get('plan_id'))
    except Exception:
        try:
            plan_id = int(request.json.get('plan_id'))
        except Exception:
            plan_id = None
    if not plan_id:
        conn.close()
        return ("Brak plan_id", 400)

    final = request.form.get('final_tonaz') or (request.json.get('final_tonaz') if request.json else None)
    note = request.form.get('note') or (request.json.get('note') if request.json else None)
    close = request.form.get('close') == '1' or (request.json.get('close') if request.json else False)

    try:
        if final is not None and final != '':
            try:
                val = int(float(str(final).replace(',', '.')))
            except Exception:
                val = None
        else:
            val = None

        sql = "UPDATE plan_produkcji SET "
        parts = []
        params = []
        if val is not None:
            parts.append('tonaz_rzeczywisty=%s')
            params.append(val)
        if note:
            parts.append('wyjasnienie_rozbieznosci=%s')
            params.append(note)
        if close:
            parts.append("status='zakonczone'")
            parts.append('real_stop=NOW()')

        if parts:
            sql += ', '.join(parts) + ' WHERE id=%s'
            params.append(plan_id)
            cursor.execute(sql, tuple(params))
            conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        try:
            conn.close()
        except Exception:
            pass

    # If called by JS, return JSON success
    try:
        from flask import jsonify
        return jsonify({'ok': True})
    except Exception:
        return redirect('/bufor')


@planista_bp.route('/bufor/archiwizuj', methods=['POST'])
@roles_required('planista', 'lider', 'admin')
def bufor_archiwizuj():
    """Endpoint obsługujący archiwizację zlecenia — zmienia status na 'archiwizowany'."""
    from flask import request, jsonify
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        try:
            plan_id = int(request.json.get('plan_id'))
        except Exception:
            plan_id = None
        
        if not plan_id:
            return jsonify({'ok': False, 'message': 'Brak plan_id'}), 400
        
        # Update status to 'archiwizowany'
        cursor.execute(
            "UPDATE plan_produkcji SET status=%s WHERE id=%s",
            ('archiwizowany', plan_id)
        )
        conn.commit()
        return jsonify({'ok': True})
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return jsonify({'ok': False, 'message': str(e)}), 500
    finally:
        try:
            conn.close()
        except Exception:
            pass