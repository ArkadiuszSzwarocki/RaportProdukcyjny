from flask import Blueprint, request, redirect, url_for, flash
from datetime import date
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
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("INSERT INTO palety_workowanie (plan_id, waga) VALUES (%s, %s)", (plan_id, float(request.form.get('waga_palety').replace(',', '.'))))
    cursor.execute("UPDATE plan_produkcji SET tonaz_rzeczywisty = (SELECT SUM(waga) / 1000 FROM palety_workowanie WHERE plan_id = %s) WHERE id = %s", (plan_id, plan_id)); conn.commit(); conn.close()
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