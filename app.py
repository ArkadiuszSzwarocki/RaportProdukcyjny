from flask import Flask, render_template, request, redirect, session, url_for, send_file, flash
from waitress import serve
from datetime import date, datetime, timedelta
import urllib.parse
import os
import json
from collections import defaultdict

# IMPORT NASZYCH NOWYCH MODUŁÓW
from config import SECRET_KEY
from db import get_db_connection, setup_database
from raporty import generuj_excel, generuj_pdf, format_godziny
from routes_admin import admin_bp
from routes_api import api_bp

app = Flask(__name__)
app.secret_key = SECRET_KEY

# --- KLUCZOWA NAPRAWA ---
# Włączamy obsługę komendy {% do %} w szablonach HTML
app.jinja_env.add_extension('jinja2.ext.do')
# ------------------------

# Rejestracja modułów
app.register_blueprint(admin_bp)
app.register_blueprint(api_bp)
app.jinja_env.filters['format_czasu'] = format_godziny

# Inicjalizacja bazy
setup_database()

# --- GLOWNE WIDOKI ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login = request.form['login']; haslo = request.form['haslo']
        conn = get_db_connection(); cursor = conn.cursor()
        cursor.execute("SELECT rola FROM uzytkownicy WHERE login = %s AND haslo = %s", (login, haslo))
        user = cursor.fetchone(); conn.close()
        if user: session['zalogowany'] = True; session['rola'] = user[0]; return redirect('/')
        return render_template('login.html', message="Błędne dane!")
    return render_template('login.html')

@app.route('/logout')
def logout(): session.clear(); return redirect('/login')

@app.route('/')
def index():
    if not session.get('zalogowany'): return redirect('/login')
    aktywna_sekcja = request.args.get('sekcja', 'Zasyp'); data_str = request.args.get('data')
    try: dzisiaj = datetime.strptime(data_str, '%Y-%m-%d').date() if data_str else date.today()
    except: dzisiaj = date.today()
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("SELECT * FROM pracownicy ORDER BY imie_nazwisko"); wszyscy = cursor.fetchall()
    cursor.execute("SELECT pracownik_id FROM obsada_zmiany WHERE data_wpisu = %s", (dzisiaj,)); zajeci_ids = [r[0] for r in cursor.fetchall()]; dostepni = [p for p in wszyscy if p[0] not in zajeci_ids]
    cursor.execute("SELECT o.id, p.imie_nazwisko FROM obsada_zmiany o JOIN pracownicy p ON o.pracownik_id = p.id WHERE o.data_wpisu = %s AND o.sekcja = %s", (dzisiaj, aktywna_sekcja)); obecna_obsada = cursor.fetchall()
    cursor.execute("SELECT d.id, p.imie_nazwisko, d.problem, d.czas_start, d.czas_stop, d.kategoria, TIMESTAMPDIFF(MINUTE, d.czas_start, d.czas_stop) FROM dziennik_zmiany d LEFT JOIN pracownicy p ON d.pracownik_id = p.id WHERE d.data_wpisu = %s AND d.sekcja = %s AND d.status='roboczy' ORDER BY d.id DESC", (dzisiaj, aktywna_sekcja)); wpisy = cursor.fetchall()
    plan_dnia = []; palety_mapa = {}; suma_plan = 0; suma_wykonanie = 0
    if aktywna_sekcja in ['Zasyp', 'Workowanie']:
        cursor.execute("SELECT id, produkt, tonaz, status, TIME_FORMAT(real_start, '%H:%i'), TIME_FORMAT(real_stop, '%H:%i'), TIMESTAMPDIFF(MINUTE, real_start, real_stop), tonaz_rzeczywisty FROM plan_produkcji WHERE data_planu = %s AND sekcja = %s ORDER BY (real_start IS NULL) ASC, real_start ASC, id ASC", (dzisiaj, aktywna_sekcja)); plan_dnia = cursor.fetchall()
        for p in plan_dnia:
            suma_plan += p[2] if p[2] else 0; suma_wykonanie += p[7] if p[7] else 0
            if aktywna_sekcja == 'Workowanie':
                cursor.execute("SELECT waga, DATE_FORMAT(data_dodania, '%H:%i') FROM palety_workowanie WHERE plan_id = %s ORDER BY id DESC", (p[0],)); palety_mapa[p[0]] = cursor.fetchall()
    cursor.execute("SELECT o.id, p.imie_nazwisko, o.typ, o.ilosc_godzin, o.komentarz FROM obecnosc o JOIN pracownicy p ON o.pracownik_id = p.id WHERE o.data_wpisu = %s", (dzisiaj,)); raporty_hr = cursor.fetchall(); conn.close()
    return render_template('dashboard.html', sekcja=aktywna_sekcja, pracownicy=dostepni, wszyscy_pracownicy=wszyscy, obsada=obecna_obsada, wpisy=wpisy, plan=plan_dnia, palety_mapa=palety_mapa, suma_plan=suma_plan, suma_wykonanie=suma_wykonanie, rola=session['rola'], dzisiaj=dzisiaj, raporty_hr=raporty_hr)

@app.route('/wyslij_raport_email', methods=['POST'])
def wyslij_raport_email():
    if not session.get('zalogowany') or session.get('rola') != 'lider': return redirect('/')
    dzisiaj = date.today(); uwagi = request.form.get('uwagi_lidera', 'Brak'); odbiorca = "zarzad@agronetzwerk.de"
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("UPDATE plan_produkcji SET status='zakonczone', real_stop=NOW() WHERE status='w toku'")
    cursor.execute("INSERT INTO raporty_koncowe (data_raportu, lider_uwagi) VALUES (%s, %s)", (dzisiaj, uwagi))
    cursor.execute("UPDATE dziennik_zmiany SET status = 'zatwierdzony' WHERE data_wpisu = %s", (dzisiaj,))
    cursor.execute("SELECT sekcja, produkt, tonaz, tonaz_rzeczywisty FROM plan_produkcji WHERE data_planu=%s", (dzisiaj,)); prod = cursor.fetchall()
    cursor.execute("SELECT sekcja, kategoria, problem, czas_start, czas_stop, TIMESTAMPDIFF(MINUTE, czas_start, czas_stop) FROM dziennik_zmiany WHERE data_wpisu=%s", (dzisiaj,)); awarie = cursor.fetchall()
    cursor.execute("SELECT p.imie_nazwisko, o.typ, o.ilosc_godzin FROM obecnosc o JOIN pracownicy p ON o.pracownik_id=p.id WHERE o.data_wpisu=%s", (dzisiaj,)); hr = cursor.fetchall()
    cursor.execute("SELECT sekcja, COALESCE(SUM(tonaz_rzeczywisty), 0) FROM plan_produkcji WHERE data_planu=%s GROUP BY sekcja", (dzisiaj,)); sumy = cursor.fetchall(); conn.commit(); conn.close()
    nazwa_xls = generuj_excel(dzisiaj, prod, awarie, hr)
    nazwa_pdf = generuj_pdf(dzisiaj, uwagi, session.get('rola').upper(), prod, awarie, hr)
    tresc = f"RAPORT ZMIANY: {dzisiaj}\nLider: {session.get('rola').upper()}\n\n--- PODSUMOWANIE ---\n"
    for r in sumy: tresc += f"{r[0]}: {r[1]} ton\n"
    tresc += f"\nUWAGI: {uwagi}\n\n(Pobierz PDF i Excel)"
    mailto = f"mailto:{odbiorca}?subject={urllib.parse.quote(f'Raport {dzisiaj}')}&body={urllib.parse.quote(tresc)}"
    session.clear()
    return render_template('raport_sent.html', excel_url=url_for('pobierz_raport', filename=nazwa_xls), pdf_url=url_for('pobierz_raport', filename=nazwa_pdf), mailto_link=mailto)

@app.route('/pobierz_raport/<filename>')
def pobierz_raport(filename): return send_file(os.path.join('raporty', filename), as_attachment=True)

@app.route('/zamknij_zmiane', methods=['POST'])
def zamknij_zmiane():
    if session.get('rola') != 'lider': return redirect('/')
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("UPDATE plan_produkcji SET status='zakonczone', real_stop=NOW() WHERE status='w toku'")
    cursor.execute("INSERT INTO raporty_koncowe (data_raportu, lider_uwagi) VALUES (%s, %s)", (date.today(), request.form.get('uwagi_lidera', '')))
    cursor.execute("UPDATE dziennik_zmiany SET status = 'zatwierdzony' WHERE data_wpisu = %s", (date.today(),))
    conn.commit(); conn.close(); flash("Zmiana zamknięta.", "success"); return redirect('/logout')

@app.route('/raporty_okresowe')
def raporty_okresowe():
    if not session.get('zalogowany'): return redirect('/login')
    teraz = datetime.now(); rok = request.args.get('rok', teraz.year, type=int); mc = request.args.get('miesiac', teraz.month, type=int)
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("SELECT COUNT(id), COALESCE(SUM(COALESCE(tonaz_rzeczywisty, tonaz)), 0), COALESCE(SUM(TIMESTAMPDIFF(MINUTE, real_start, real_stop)), 0) FROM plan_produkcji WHERE YEAR(data_planu)=%s AND MONTH(data_planu)=%s AND status='zakonczone'", (rok, mc)); stats = cursor.fetchone()
    cursor.execute("SELECT kategoria, COUNT(id), COALESCE(SUM(TIMESTAMPDIFF(MINUTE, czas_start, czas_stop)), 0) FROM dziennik_zmiany WHERE YEAR(data_wpisu)=%s AND MONTH(data_wpisu)=%s GROUP BY kategoria", (rok, mc)); awarie = cursor.fetchall()
    cursor.execute("SELECT MONTH(data_planu), COALESCE(SUM(COALESCE(tonaz_rzeczywisty, tonaz)), 0) FROM plan_produkcji WHERE YEAR(data_planu)=%s AND status='zakonczone' GROUP BY MONTH(data_planu) ORDER BY MONTH(data_planu)", (rok,)); trend = cursor.fetchall(); conn.close()
    labels = [['Sty','Lut','Mar','Kwi','Maj','Cze','Lip','Sie','Wrz','Paź','Lis','Gru'][r[0]-1] for r in trend]; data = [r[1] for r in trend]
    return render_template('raporty_okresowe.html', rok=rok, miesiac=mc, stats=stats, awarie=awarie, labels_rok=labels, data_rok=data)

@app.route('/zarzad')
def zarzad_panel():
    if not session.get('zalogowany'): return redirect('/login')
    tryb = request.args.get('tryb', 'miesiac'); teraz = datetime.now()
    if tryb == 'dzien': d = request.args.get('data') or str(teraz.date()); d_od = d_do = d; tytul = f"Dzienny: {d}"
    elif tryb == 'tydzien': rok = int(request.args.get('rok', teraz.year)); tydz = int(request.args.get('tydzien', teraz.isocalendar()[1])); d_od = datetime.strptime(f"{rok}-W{tydz}-1", "%Y-W%W-%w").date(); d_do = d_od + timedelta(days=6); tytul = "Tygodniowy"
    elif tryb == 'miesiac': rok = int(request.args.get('rok', teraz.year)); mc = int(request.args.get('miesiac', teraz.month)); d_od = date(rok, mc, 1); d_do = (date(rok, mc+1, 1) - timedelta(days=1)) if mc < 12 else date(rok, 12, 31); tytul = "Miesięczny"
    elif tryb == 'rok': rok = int(request.args.get('rok', teraz.year)); d_od = date(rok, 1, 1); d_do = date(rok, 12, 31); tytul = f"Roczny {rok}"
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("SELECT COALESCE(SUM(tonaz), 0), COALESCE(SUM(tonaz_rzeczywisty), 0), COUNT(id) FROM plan_produkcji WHERE data_planu BETWEEN %s AND %s AND status='zakonczone'", (d_od, d_do)); kpi = cursor.fetchone()
    cursor.execute("SELECT data_planu, SUM(tonaz), SUM(COALESCE(tonaz_rzeczywisty, 0)) FROM plan_produkcji WHERE data_planu BETWEEN %s AND %s GROUP BY data_planu ORDER BY data_planu", (d_od, d_do)); ch = cursor.fetchall(); ch_l = [str(r[0]) for r in ch]; ch_p = [r[1] for r in ch]; ch_w = [r[2] for r in ch]
    cursor.execute("SELECT kategoria, COALESCE(SUM(TIMESTAMPDIFF(MINUTE, czas_start, czas_stop)), 0) FROM dziennik_zmiany WHERE data_wpisu BETWEEN %s AND %s GROUP BY kategoria", (d_od, d_do)); dt = cursor.fetchall(); pie_l = [r[0] for r in dt]; pie_v = [r[1] for r in dt]
    p_stats = []
    if tryb == 'dzien':
        cursor.execute("SELECT id, imie_nazwisko FROM pracownicy ORDER BY imie_nazwisko"); all_p = cursor.fetchall(); p_dict = {p[1]: {'zasyp':'-','workowanie':'-','magazyn':'-','hr':'-'} for p in all_p}
        cursor.execute("SELECT p.imie_nazwisko, o.sekcja FROM obsada_zmiany o JOIN pracownicy p ON o.pracownik_id=p.id WHERE o.data_wpisu=%s", (d_od,)); 
        for r in cursor.fetchall(): 
            if r[1] in ['Zasyp','Workowanie','Magazyn']: p_dict[r[0]][r[1].lower()] = '✅'
        cursor.execute("SELECT p.imie_nazwisko, o.typ FROM obecnosc o JOIN pracownicy p ON o.pracownik_id=p.id WHERE o.data_wpisu=%s", (d_od,)); 
        for r in cursor.fetchall(): p_dict[r[0]]['hr'] = r[1]
        p_stats = [{'name': k, **v} for k, v in p_dict.items()]
    else:
        cursor.execute("SELECT p.imie_nazwisko, COUNT(o.id) FROM obsada_zmiany o JOIN pracownicy p ON o.pracownik_id=p.id WHERE o.data_wpisu BETWEEN %s AND %s GROUP BY p.imie_nazwisko", (d_od, d_do)); 
        p_dict = defaultdict(lambda: {'total':0,'abs':0,'ot':0}); 
        for r in cursor.fetchall(): p_dict[r[0]]['total'] = r[1]
        cursor.execute("SELECT p.imie_nazwisko, o.typ, SUM(o.ilosc_godzin) FROM obecnosc o JOIN pracownicy p ON o.pracownik_id=p.id WHERE o.data_wpisu BETWEEN %s AND %s GROUP BY p.imie_nazwisko, o.typ", (d_od, d_do)); 
        for r in cursor.fetchall(): p_dict[r[0]]['abs' if r[1]=='Nieobecność' else 'ot'] = r[2]
        p_stats = [{'name': k, **v} for k, v in p_dict.items()]; p_stats.sort(key=lambda x: x['total'], reverse=True)
    conn.close()
    return render_template('zarzad.html', tryb=tryb, tytul=tytul, suma_plan=kpi[0], suma_wykonanie=kpi[1], ilosc_zlecen=kpi[2], procent=(kpi[1]/kpi[0]*100) if kpi[0] else 0, time_aw=sum(pie_v), chart_labels=json.dumps(ch_l), chart_plan=json.dumps(ch_p), chart_wyk=json.dumps(ch_w), pie_labels=json.dumps(pie_l), pie_values=json.dumps(pie_v), pracownicy_stats=p_stats)

if __name__ == '__main__':
    print("🚀 Serwer wystartował: http://YOUR_IP_ADDRESS:8082")
    serve(app, host='0.0.0.0', port=8082, threads=6)