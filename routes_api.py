from flask import Blueprint, request, redirect, url_for, flash, session
from datetime import date, datetime
from db import get_db_connection
# Importujemy nasz nowy dekorator
from decorators import login_required

api_bp = Blueprint('api', __name__)

@api_bp.route('/dodaj_plan', methods=['POST'])
@login_required
def dodaj_plan():
    sekcja = request.form.get('sekcja', 'Zasyp')
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("INSERT INTO plan_produkcji (data_planu, produkt, tonaz, status, sekcja) VALUES (%s, %s, %s, 'zaplanowane', %s)", (request.form['data_planu'], request.form['produkt'], request.form['tonaz'], sekcja)); conn.commit(); conn.close()
    return redirect(url_for('index', sekcja=sekcja, data=request.form['data_planu']))

@api_bp.route('/usun_plan/<int:id>', methods=['POST'])
@login_required
def usun_plan(id):
    conn = get_db_connection(); cursor = conn.cursor(); cursor.execute("DELETE FROM plan_produkcji WHERE id=%s", (id,)); conn.commit(); conn.close()
    return redirect(url_for('index', sekcja='Zasyp', data=request.form.get('data_powrotu', date.today())))

@api_bp.route('/start_zlecenie/<int:id>', methods=['POST'])
@login_required
def start_zlecenie(id):
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("SELECT produkt, tonaz, sekcja, data_planu FROM plan_produkcji WHERE id=%s", (id,)); z = cursor.fetchone()
    cursor.execute("UPDATE plan_produkcji SET status='zakonczone', real_stop=NOW() WHERE status='w toku' AND id!=%s AND sekcja=(SELECT sekcja FROM plan_produkcji WHERE id=%s)", (id, id))
    cursor.execute("UPDATE plan_produkcji SET status='w toku', real_start=NOW() WHERE id=%s", (id,))
    if z and z[2] == 'Zasyp':
        cursor.execute("SELECT id FROM plan_produkcji WHERE data_planu=%s AND produkt=%s AND tonaz=%s AND sekcja='Workowanie'", (z[3], z[0], z[1]))
        if not cursor.fetchone(): cursor.execute("INSERT INTO plan_produkcji (data_planu, sekcja, produkt, tonaz, status) VALUES (%s, 'Workowanie', %s, %s, 'zaplanowane')", (z[3], z[0], z[1]))
    conn.commit(); conn.close(); return redirect(url_for('index', sekcja=request.args.get('sekcja', 'Zasyp'), data=request.form.get('data_powrotu', date.today())))

@api_bp.route('/koniec_zlecenie/<int:id>', methods=['POST'])
@login_required
def koniec_zlecenie(id):
    conn = get_db_connection(); cursor = conn.cursor(); cursor.execute("UPDATE plan_produkcji SET status='zakonczone', real_stop=NOW() WHERE id=%s", (id,)); conn.commit(); conn.close()
    return redirect(url_for('index', sekcja=request.args.get('sekcja', 'Zasyp'), data=request.form.get('data_powrotu', date.today())))

@api_bp.route('/start_przejscie', methods=['POST'])
@login_required
def start_przejscie():
    conn = get_db_connection(); cursor = conn.cursor(); cursor.execute("UPDATE plan_produkcji SET status='zakonczone', real_stop=NOW() WHERE status='w toku'")
    cursor.execute("INSERT INTO plan_produkcji (data_planu, produkt, tonaz, status, real_start) VALUES (%s, 'PRZEJŚCIE / ZMIANA', 0, 'w toku', NOW())", (request.form.get('data_powrotu', date.today()),)); conn.commit(); conn.close()
    return redirect(url_for('index', sekcja='Zasyp', data=request.form.get('data_powrotu', date.today())))

@api_bp.route('/zapisz_tonaz/<int:id>', methods=['POST'])
@login_required
def zapisz_tonaz(id):
    conn = get_db_connection(); cursor = conn.cursor()
    tonaz = request.form.get('tonaz_rzeczywisty').replace(',', '.') if request.form.get('tonaz_rzeczywisty') else None
    cursor.execute("UPDATE plan_produkcji SET tonaz_rzeczywisty=%s WHERE id=%s", (tonaz, id)); conn.commit(); conn.close()
    return redirect(url_for('index', sekcja='Zasyp', data=request.form.get('data_powrotu', date.today())))

@api_bp.route('/dodaj_palete/<int:plan_id>', methods=['POST'])
@login_required
def dodaj_palete(plan_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Dodaj paletę
    waga = float(request.form.get('waga_palety').replace(',', '.'))
    cursor.execute("INSERT INTO palety_workowanie (plan_id, waga) VALUES (%s, %s)", (plan_id, waga))
    
    # 2. Zaktualizuj tonaż w Workowaniu
    cursor.execute("UPDATE plan_produkcji SET tonaz_rzeczywisty = (SELECT SUM(waga) / 1000 FROM palety_workowanie WHERE plan_id = %s) WHERE id = %s", (plan_id, plan_id))
    
    # --- NOWA LOGIKA: AUTOMATYZACJA MAGAZYNU ---
    # Pobierz dane obecnego zlecenia (Workowanie)
    cursor.execute("SELECT data_planu, produkt, tonaz FROM plan_produkcji WHERE id=%s", (plan_id,))
    zlecenie = cursor.fetchone()
    
    if zlecenie:
        data_planu, produkt, tonaz = zlecenie
        
        # Sprawdź, czy istnieje już zlecenie na Magazyn dla tego produktu i daty
        cursor.execute("""
            SELECT id FROM plan_produkcji 
            WHERE data_planu=%s AND produkt=%s AND sekcja='Magazyn' AND tonaz=%s
        """, (data_planu, produkt, tonaz))
        
        istnieje_magazyn = cursor.fetchone()
        
        # Jeśli to pierwsza paleta i nie ma zlecenia na Magazynie -> TWORZYMY JE
        if not istnieje_magazyn:
            cursor.execute("""
                INSERT INTO plan_produkcji (data_planu, sekcja, produkt, tonaz, status, kolejnosc) 
                VALUES (%s, 'Magazyn', %s, %s, 'zaplanowane', 999)
            """, (data_planu, produkt, tonaz))
    # -------------------------------------------

    conn.commit()
    conn.close()
    return redirect(url_for('index', sekcja='Workowanie', data=request.form.get('data_powrotu')))

@api_bp.route('/cofnij_palete/<int:plan_id>', methods=['POST'])
@login_required
def cofnij_palete(plan_id):
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("DELETE FROM palety_workowanie WHERE plan_id=%s ORDER BY id DESC LIMIT 1", (plan_id,))
    cursor.execute("UPDATE plan_produkcji SET tonaz_rzeczywisty = COALESCE((SELECT SUM(waga) / 1000 FROM palety_workowanie WHERE plan_id = %s), 0) WHERE id = %s", (plan_id, plan_id)); conn.commit(); conn.close()
    return redirect(url_for('index', sekcja='Workowanie', data=request.form.get('data_powrotu')))

@api_bp.route('/dodaj_obecnosc', methods=['POST'])
@login_required
def dodaj_obecnosc():
    typ = request.form['typ']; komentarz = request.form.get('komentarz', '').strip()
    if typ == 'Nadgodziny' and not komentarz: flash("BŁĄD: Wymagany powód nadgodzin!", "error"); return redirect(url_for('index') + '#panel-lidera')
    conn = get_db_connection(); cursor = conn.cursor(); cursor.execute("INSERT INTO obecnosc (data_wpisu, pracownik_id, typ, ilosc_godzin, komentarz) VALUES (%s, %s, %s, %s, %s)", (request.form.get('data_wpisu', date.today()), request.form['pracownik_id'], typ, request.form.get('godziny', 0), komentarz)); conn.commit(); conn.close()
    return redirect(url_for('index') + '#panel-lidera')

@api_bp.route('/usun_obecnosc/<int:id>', methods=['POST'])
@login_required
def usun_obecnosc(id):
    conn = get_db_connection(); cursor = conn.cursor(); cursor.execute("DELETE FROM obecnosc WHERE id=%s", (id,)); conn.commit(); conn.close()
    return redirect(url_for('index') + '#panel-lidera')

@api_bp.route('/dodaj_do_obsady', methods=['POST'])
@login_required
def dodaj_do_obsady():
    conn = get_db_connection(); cursor = conn.cursor(); cursor.execute("INSERT INTO obsada_zmiany (data_wpisu, sekcja, pracownik_id) VALUES (%s, %s, %s)", (date.today(), request.form['sekcja'], request.form['pracownik_id'])); conn.commit(); conn.close()
    return redirect(url_for('index', sekcja=request.form['sekcja']))

@api_bp.route('/usun_z_obsady/<int:id>', methods=['POST'])
@login_required
def usun_z_obsady(id):
    conn = get_db_connection(); cursor = conn.cursor(); cursor.execute("DELETE FROM obsada_zmiany WHERE id = %s", (id,)); conn.commit(); conn.close()
    return redirect(url_for('index', sekcja=request.form['sekcja']))

@api_bp.route('/dodaj_wpis', methods=['POST'])
@login_required
def dodaj_wpis():
    conn = get_db_connection(); cursor = conn.cursor(); cursor.execute("INSERT INTO dziennik_zmiany (data_wpisu, sekcja, problem, czas_start, status, kategoria) VALUES (%s, %s, %s, %s, 'roboczy', %s)", (date.today(), request.form['sekcja'], request.form.get('problem'), request.form.get('czas_start') or datetime.now().strftime("%H:%M"), request.form['kategoria'])); conn.commit(); conn.close()
    return redirect(url_for('index', sekcja=request.form['sekcja']))

@api_bp.route('/usun_wpis/<int:id>', methods=['POST'])
@login_required
def usun_wpis(id):
    conn = get_db_connection(); cursor = conn.cursor(); cursor.execute("DELETE FROM dziennik_zmiany WHERE id = %s", (id,)); conn.commit(); conn.close()
    return redirect(url_for('index', sekcja=request.form['sekcja']))

@api_bp.route('/edytuj/<int:id>', methods=['GET', 'POST'])
@login_required
def edytuj(id):
    conn = get_db_connection(); cursor = conn.cursor()
    if request.method == 'POST': cursor.execute("UPDATE dziennik_zmiany SET problem=%s, kategoria=%s, czas_start=%s, czas_stop=%s WHERE id=%s", (request.form.get('problem'), request.form.get('kategoria'), request.form.get('czas_start') or None, request.form.get('czas_stop') or None, id)); conn.commit(); conn.close(); return redirect('/')
    cursor.execute("SELECT * FROM dziennik_zmiany WHERE id = %s", (id,)); wpis = cursor.fetchone(); conn.close(); return render_template('edycja.html', wpis=wpis)

# --- NOWE FUNKCJE DLA PLANISTY ---

# routes_api.py - ZMODYFIKOWANA funkcja dodaj_plan_zaawansowany

@api_bp.route('/dodaj_plan_zaawansowany', methods=['POST'])
@login_required
def dodaj_plan_zaawansowany():
    if session.get('rola') not in ['planista', 'admin']: return redirect('/')
    
    sekcja = request.form.get('sekcja')
    data_planu = request.form.get('data_planu')
    produkt = request.form.get('produkt')
    tonaz = request.form.get('tonaz')
    wymaga_oplaty = request.form.get('wymaga_oplaty')
    status = 'nieoplacone' if wymaga_oplaty else 'zaplanowane'

    conn = get_db_connection()
    cursor = conn.cursor()
    
    # --- NOWE: Obliczamy następny numer kolejności dla tego dnia ---
    cursor.execute("SELECT MAX(kolejnosc) FROM plan_produkcji WHERE data_planu=%s", (data_planu,))
    max_k = cursor.fetchone()[0]
    next_k = (max_k + 1) if max_k else 1
    # ---------------------------------------------------------------

    cursor.execute(
        "INSERT INTO plan_produkcji (data_planu, produkt, tonaz, status, sekcja, kolejnosc) VALUES (%s, %s, %s, %s, %s, %s)",
        (data_planu, produkt, tonaz, status, sekcja, next_k)
    )
    conn.commit()
    conn.close()
    return redirect(url_for('planista.panel_planisty', data=data_planu))

@api_bp.route('/zmien_status_zlecenia/<int:id>', methods=['POST'])
@login_required
def zmien_status_zlecenia(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE plan_produkcji SET status=%s WHERE id=%s", (request.form.get('status'), id))
    conn.commit()
    conn.close()
    
    return redirect(url_for('planista.panel_planisty', data=request.form.get('data_powrotu')))

@api_bp.route('/przenies_zlecenie/<int:id>', methods=['POST'])
@login_required
def przenies_zlecenie(id):
    if request.form.get('nowa_data'):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE plan_produkcji SET data_planu=%s WHERE id=%s", (request.form.get('nowa_data'), id))
        conn.commit()
        conn.close()
    
    return redirect(url_for('planista.panel_planisty', data=request.form.get('stara_data')))

@api_bp.route('/przesun_zlecenie/<int:id>/<kierunek>', methods=['POST'])
@login_required
def przesun_zlecenie(id, kierunek):
    if session.get('rola') not in ['planista', 'admin']:
        return redirect('/')
    
    data_powrotu = request.args.get('data', str(date.today()))
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Pobierz dane obecnego zlecenia
    cursor.execute("SELECT id, kolejnosc, data_planu FROM plan_produkcji WHERE id=%s", (id,))
    obecne = cursor.fetchone()
    
    if obecne:
        obecne_id, obecna_kol, data = obecne
        if obecna_kol is None: obecna_kol = 0 # Zabezpieczenie

        # 2. Znajdź sąsiada do zamiany
        sasiad = None
        if kierunek == 'gora':
            # Szukamy zlecenia z mniejszą kolejnością (czyli wyżej na liście), ale najbliższego
            query = "SELECT id, kolejnosc FROM plan_produkcji WHERE data_planu=%s AND kolejnosc < %s ORDER BY kolejnosc DESC LIMIT 1"
        else: # dol
            # Szukamy zlecenia z większą kolejnością (niżej), najbliższego
            query = "SELECT id, kolejnosc FROM plan_produkcji WHERE data_planu=%s AND kolejnosc > %s ORDER BY kolejnosc ASC LIMIT 1"
            
        cursor.execute(query, (data, obecna_kol))
        sasiad = cursor.fetchone()

        # 3. Zamiana miejscami (swap)
        if sasiad:
            sasiad_id, sasiad_kol = sasiad
            # Aktualizujemy oba rekordy
            cursor.execute("UPDATE plan_produkcji SET kolejnosc=%s WHERE id=%s", (sasiad_kol, obecne_id))
            cursor.execute("UPDATE plan_produkcji SET kolejnosc=%s WHERE id=%s", (obecna_kol, sasiad_id))
            conn.commit()

    conn.close()
    return redirect(url_for('planista.panel_planisty', data=data_powrotu))