from flask import Flask, render_template, request, redirect, session, url_for, send_file, flash
import logging
from logging.handlers import RotatingFileHandler
import os
import threading
import time
from waitress import serve
from datetime import date, datetime, timedelta
import os
import json
from collections import defaultdict

from config import SECRET_KEY
from werkzeug.security import check_password_hash
from db import get_db_connection, setup_database
from raporty import format_godziny
from routes_admin import admin_bp
from routes_api import api_bp
from routes_planista import planista_bp
from decorators import login_required, zarzad_required

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.jinja_env.add_extension('jinja2.ext.do')
app.register_blueprint(admin_bp)
app.register_blueprint(api_bp)
app.register_blueprint(planista_bp)
app.jinja_env.filters['format_czasu'] = format_godziny
setup_database()

# Logging: zapisz pełne błędy do pliku logs/app.log
logs_dir = os.path.join(os.path.dirname(__file__), 'logs')
if not os.path.exists(logs_dir):
    os.makedirs(logs_dir)
log_path = os.path.join(logs_dir, 'app.log')
handler = RotatingFileHandler(log_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding='utf-8')
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]')
handler.setFormatter(formatter)
app.logger.setLevel(logging.DEBUG)
app.logger.addHandler(handler)
logging.getLogger('werkzeug').addHandler(handler)


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    # Zarejestruj pełen traceback w logu i zwróć przyjazny komunikat użytkownikowi
    try:
        from flask import request
        app.logger.exception('Unhandled exception on %s %s: %s', request.method, request.path, error)
    except Exception:
        app.logger.exception('Unhandled exception: %s', error)
    return render_template('500.html') if os.path.exists(os.path.join(app.template_folder or '', '500.html')) else ("Wewnętrzny błąd serwera", 500)


def _cleanup_old_reports(folder='raporty', max_age_hours=24, interval_seconds=3600):
    """Wątek: usuwa pliki w `folder` starsze niż `max_age_hours` co `interval_seconds`."""
    try:
        while True:
            try:
                if os.path.exists(folder):
                    now = time.time()
                    max_age = max_age_hours * 3600
                    for name in os.listdir(folder):
                        path = os.path.join(folder, name)
                        try:
                            if os.path.isfile(path):
                                mtime = os.path.getmtime(path)
                                if now - mtime > max_age:
                                    try:
                                        os.remove(path)
                                        app.logger.info('Removed old report file: %s', path)
                                    except Exception:
                                        app.logger.exception('Failed to remove file: %s', path)
                        except Exception:
                            app.logger.exception('Error checking file: %s', path)
            except Exception:
                app.logger.exception('Error in cleanup loop')
            time.sleep(interval_seconds)
    except Exception:
        app.logger.exception('Cleanup thread terminating unexpectedly')


# Start cleanup thread (daemon) to remove old report files
try:
    cleanup_thread = threading.Thread(target=_cleanup_old_reports, kwargs={'folder':'raporty','max_age_hours':24,'interval_seconds':3600}, daemon=True)
    cleanup_thread.start()
except Exception:
    app.logger.exception('Failed to start cleanup thread')



@app.before_request
def log_request_info():
    try:
        from flask import request
        app.logger.debug('Incoming request: %s %s', request.method, request.path)
    except Exception:
        pass

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        conn = get_db_connection(); cursor = conn.cursor()
        cursor.execute("SELECT id, haslo, rola FROM uzytkownicy WHERE login = %s", (request.form['login'],))
        row = cursor.fetchone(); conn.close()
        if row:
            uid, hashed, rola = row[0], row[1], row[2]
            if hashed and check_password_hash(hashed, request.form['haslo']):
                session['zalogowany'] = True; session['rola'] = rola
                return redirect('/planista' if rola == 'planista' else '/')
        flash("Błędne dane!", 'danger')
        return redirect('/login')
    return render_template('login.html')

@app.route('/logout')
def logout(): session.clear(); return redirect('/login')

@app.route('/')
@login_required
def index():
    aktywna_sekcja = request.args.get('sekcja', 'Zasyp')
    try: dzisiaj = datetime.strptime(request.args.get('data'), '%Y-%m-%d').date() if request.args.get('data') else date.today()
    except: dzisiaj = date.today()
    conn = get_db_connection(); cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM pracownicy ORDER BY imie_nazwisko"); wszyscy = cursor.fetchall()
    cursor.execute("SELECT pracownik_id FROM obsada_zmiany WHERE data_wpisu = %s", (dzisiaj,)); zajeci_ids = [r[0] for r in cursor.fetchall()]
    dostepni = [p for p in wszyscy if p[0] not in zajeci_ids]
    cursor.execute("SELECT o.id, p.imie_nazwisko FROM obsada_zmiany o JOIN pracownicy p ON o.pracownik_id = p.id WHERE o.data_wpisu = %s AND o.sekcja = %s", (dzisiaj, aktywna_sekcja)); obecna_obsada = cursor.fetchall()
    cursor.execute("SELECT d.id, p.imie_nazwisko, d.problem, TIME_FORMAT(d.czas_start, '%H:%i'), d.czas_stop, d.kategoria, TIMESTAMPDIFF(MINUTE, d.czas_start, d.czas_stop) FROM dziennik_zmiany d LEFT JOIN pracownicy p ON d.pracownik_id = p.id WHERE d.data_wpisu = %s AND d.sekcja = %s AND d.status='roboczy' ORDER BY d.id DESC", (dzisiaj, aktywna_sekcja)); wpisy = cursor.fetchall()
    
    plan_dnia = []; palety_mapa = {}; magazyn_palety = []; suma_plan = 0; suma_wykonanie = 0
    cursor.execute("SELECT DISTINCT produkt FROM plan_produkcji WHERE sekcja='Zasyp' AND status IN ('w toku', 'zakonczone') AND data_planu = %s", (dzisiaj,)); zasyp_rozpoczete = [r[0] for r in cursor.fetchall()]
    
    if aktywna_sekcja == 'Magazyn':
        cursor.execute("SELECT p.produkt, pw.waga, DATE_FORMAT(pw.data_dodania, '%H:%i'), pw.id, pw.plan_id FROM palety_workowanie pw JOIN plan_produkcji p ON pw.plan_id = p.id WHERE DATE(pw.data_dodania) = %s AND pw.waga > 0", (dzisiaj,)); magazyn_palety = cursor.fetchall()

    cursor.execute("SELECT id, produkt, tonaz, status, TIME_FORMAT(real_start, '%H:%i'), TIME_FORMAT(real_stop, '%H:%i'), TIMESTAMPDIFF(MINUTE, real_start, real_stop), tonaz_rzeczywisty, kolejnosc, typ_produkcji, wyjasnienie_rozbieznosci FROM plan_produkcji WHERE data_planu = %s AND sekcja = %s AND status != 'nieoplacone' ORDER BY CASE status WHEN 'w toku' THEN 1 WHEN 'zaplanowane' THEN 2 ELSE 3 END, kolejnosc ASC, id ASC", (dzisiaj, aktywna_sekcja))
    plan_dnia = [list(r) for r in cursor.fetchall()]
    
    for p in plan_dnia:
        if p[7] is None: p[7] = 0
        suma_plan += p[2] if p[2] else 0
        current_wykonanie = p[7]
        
        if aktywna_sekcja == 'Magazyn':
            cursor.execute("SELECT pw.waga, DATE_FORMAT(pw.data_dodania, '%H:%i'), pw.id, pw.plan_id, p.typ_produkcji, pw.tara, pw.waga_brutto FROM palety_workowanie pw JOIN plan_produkcji p ON pw.plan_id = p.id WHERE p.data_planu = %s AND p.produkt = %s AND p.sekcja = 'Workowanie' ORDER BY pw.id DESC", (dzisiaj, p[1]))
            palety = cursor.fetchall()
            palety_mapa[p[0]] = palety
            # SUMA W KG (BEZ DZIELENIA)
            waga_kg = sum(pal[0] for pal in palety)
            p[7] = waga_kg
            suma_wykonanie += waga_kg
        elif aktywna_sekcja == 'Workowanie':
            cursor.execute("SELECT pw.waga, DATE_FORMAT(pw.data_dodania, '%H:%i'), pw.id, pw.plan_id, p.typ_produkcji, pw.tara, pw.waga_brutto FROM palety_workowanie pw JOIN plan_produkcji p ON pw.plan_id = p.id WHERE pw.plan_id = %s ORDER BY pw.id DESC", (p[0],)); palety = cursor.fetchall()
            palety_mapa[p[0]] = palety
            suma_wykonanie += current_wykonanie
        else:
            suma_wykonanie += current_wykonanie

        waga_workowania = 0; diff = 0; alert = False
        if aktywna_sekcja == 'Zasyp':
            cursor.execute("SELECT SUM(tonaz_rzeczywisty) FROM plan_produkcji WHERE data_planu=%s AND produkt=%s AND sekcja='Workowanie' AND typ_produkcji=%s", (dzisiaj, p[1], p[9]))
            res = cursor.fetchone()
            waga_workowania = res[0] if res and res[0] else 0
            if p[7]:
                diff = p[7] - waga_workowania
                if abs(diff) > 10: alert = True # Tolerancja 10kg
        p.extend([waga_workowania, diff, alert])

    next_workowanie_id = None
    if aktywna_sekcja == 'Workowanie':
        kandydaci = [p for p in plan_dnia if p[3] == 'zaplanowane']
        kandydaci.sort(key=lambda x: x[0])
        if kandydaci: next_workowanie_id = kandydaci[0][0]

    cursor.execute("SELECT o.id, p.imie_nazwisko, o.typ, o.ilosc_godzin, o.komentarz FROM obecnosc o JOIN pracownicy p ON o.pracownik_id = p.id WHERE o.data_wpisu = %s", (dzisiaj,)); raporty_hr = cursor.fetchall(); conn.close()
    return render_template('dashboard.html', sekcja=aktywna_sekcja, pracownicy=dostepni, wszyscy_pracownicy=wszyscy, obsada=obecna_obsada, wpisy=wpisy, plan=plan_dnia, palety_mapa=palety_mapa, magazyn_palety=magazyn_palety, suma_plan=suma_plan, suma_wykonanie=suma_wykonanie, rola=session.get('rola'), dzisiaj=dzisiaj, raporty_hr=raporty_hr, zasyp_rozpoczete=zasyp_rozpoczete, next_workowanie_id=next_workowanie_id, now_time=datetime.now().strftime('%H:%M'))

@app.route('/zarzad')
@zarzad_required
def zarzad_panel():
    teraz = datetime.now(); tryb = request.args.get('tryb', 'miesiac')
    def get_arg_int(key, default):
        try: return int(request.args.get(key))
        except: return default
    wybrany_rok = get_arg_int('rok', teraz.year); wybrany_miesiac = get_arg_int('miesiac', teraz.month); wybrana_data = request.args.get('data') or str(teraz.date())
    if tryb == 'dzien': d_od = d_do = wybrana_data; tytul = f"Dzienny: {wybrana_data}"
    elif tryb == 'rok': d_od = date(wybrany_rok, 1, 1); d_do = date(wybrany_rok, 12, 31); tytul = f"Roczny {wybrany_rok}"
    else: d_od = date(wybrany_rok, wybrany_miesiac, 1); d_do = (date(wybrany_rok, wybrany_miesiac+1, 1) - timedelta(days=1)) if wybrany_miesiac < 12 else date(wybrany_rok, 12, 31); tytul = f"Miesięczny ({wybrany_rok}-{wybrany_miesiac:02d})"
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("SELECT COALESCE(SUM(CASE WHEN sekcja='Zasyp' THEN tonaz ELSE 0 END), 0), COALESCE(SUM(CASE WHEN sekcja='Workowanie' THEN tonaz_rzeczywisty ELSE 0 END), 0), COUNT(id) FROM plan_produkcji WHERE data_planu BETWEEN %s AND %s AND status='zakonczone'", (d_od, d_do)); kpi = cursor.fetchone()
    cursor.execute("SELECT data_planu, SUM(CASE WHEN sekcja = 'Zasyp' THEN tonaz ELSE 0 END), SUM(CASE WHEN sekcja = 'Zasyp' THEN COALESCE(tonaz_rzeczywisty, 0) ELSE 0 END), SUM(CASE WHEN sekcja = 'Workowanie' THEN COALESCE(tonaz_rzeczywisty, 0) ELSE 0 END) FROM plan_produkcji WHERE data_planu BETWEEN %s AND %s GROUP BY data_planu ORDER BY data_planu", (d_od, d_do)); ch = cursor.fetchall()
    ch_l = [str(r[0]) for r in ch]; ch_plan = [float(r[1]) for r in ch]; ch_zasyp = [float(r[2]) for r in ch]; ch_work = [float(r[3]) for r in ch]
    cursor.execute("SELECT kategoria, COALESCE(SUM(TIMESTAMPDIFF(MINUTE, czas_start, czas_stop)), 0) FROM dziennik_zmiany WHERE data_wpisu BETWEEN %s AND %s GROUP BY kategoria", (d_od, d_do)); dt = cursor.fetchall(); pie_l = [r[0] for r in dt]; pie_v = [float(r[1]) for r in dt]
    p_stats = []
    if tryb == 'dzien':
        cursor.execute("SELECT id, imie_nazwisko FROM pracownicy ORDER BY imie_nazwisko"); all_p = cursor.fetchall(); p_dict = {p[1]: {'zasyp':'-','workowanie':'-','magazyn':'-','hr':'-'} for p in all_p}
        cursor.execute("SELECT p.imie_nazwisko, o.sekcja FROM obsada_zmiany o JOIN pracownicy p ON o.pracownik_id=p.id WHERE o.data_wpisu=%s", (d_od,)); 
        for r in cursor.fetchall(): p_dict[r[0]][r[1].lower()] = '✅'
        cursor.execute("SELECT p.imie_nazwisko, o.typ FROM obecnosc o JOIN pracownicy p ON o.pracownik_id=p.id WHERE o.data_wpisu=%s", (d_od,)); 
        for r in cursor.fetchall(): p_dict[r[0]]['hr'] = r[1]
        p_stats = [{'name': k, **v} for k, v in p_dict.items()]
    else:
        cursor.execute("SELECT p.imie_nazwisko, COUNT(o.id) FROM obsada_zmiany o JOIN pracownicy p ON o.pracownik_id=p.id WHERE o.data_wpisu BETWEEN %s AND %s GROUP BY p.imie_nazwisko", (d_od, d_do)); p_dict = defaultdict(lambda: {'total':0,'abs':0,'ot':0})
        for r in cursor.fetchall(): p_dict[r[0]]['total'] = r[1]
        cursor.execute("SELECT p.imie_nazwisko, o.typ, SUM(o.ilosc_godzin) FROM obecnosc o JOIN pracownicy p ON o.pracownik_id=p.id WHERE o.data_wpisu BETWEEN %s AND %s GROUP BY p.imie_nazwisko, o.typ", (d_od, d_do))
        for r in cursor.fetchall(): p_dict[r[0]]['abs' if r[1]=='Nieobecność' else 'ot'] = r[2]
        p_stats = [{'name': k, **v} for k, v in p_dict.items()]; p_stats.sort(key=lambda x: x['total'], reverse=True)
    conn.close(); return render_template('zarzad.html', tryb=tryb, tytul=tytul, wybrany_rok=wybrany_rok, wybrany_miesiac=wybrany_miesiac, wybrana_data=wybrana_data, suma_plan=kpi[0], suma_wykonanie=kpi[1], ilosc_zlecen=kpi[2], procent=(kpi[1]/kpi[0]*100) if kpi[0] else 0, time_aw=sum(pie_v), chart_labels=json.dumps(ch_l), chart_plan=json.dumps(ch_plan), chart_zasyp=json.dumps(ch_zasyp), chart_work=json.dumps(ch_work), pie_labels=json.dumps(pie_l), pie_values=json.dumps(pie_v), pracownicy_stats=p_stats)

@app.route('/pobierz_raport/<filename>')
@login_required
def pobierz_raport(filename): return send_file(os.path.join('raporty', filename), as_attachment=True)


@app.route('/pobierz_logi')
@login_required
def pobierz_logi():
    """Tymczasowy, chroniony endpoint do pobrania pliku logów aplikacji.

    Dostęp: tylko role 'admin' i 'zarzad'. Zwraca `app.log` jako załącznik.
    """
    if session.get('rola') not in ['admin', 'zarzad']:
        return ("Brak dostępu", 403)
    log_path = os.path.join(os.path.dirname(__file__), 'logs', 'app.log')
    if not os.path.exists(log_path):
        return ("Brak logu", 404)
    return send_file(log_path, as_attachment=True)

@app.route('/zamknij_zmiane', methods=['POST'])
@login_required
def zamknij_zmiane():
    from generator_raportow import generuj_excel_zmiany, otworz_outlook_z_raportem
    import os

    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Zamykamy zlecenia
    cursor.execute("UPDATE plan_produkcji SET status='zakonczone', real_stop=NOW() WHERE status='w toku'")
    uwagi = request.form.get('uwagi_lidera', '')
    cursor.execute("INSERT INTO raporty_koncowe (data_raportu, lider_uwagi) VALUES (%s, %s)", (date.today(), uwagi))
    conn.commit()
    conn.close()
    
    # 2. Generujemy raporty (Excel + notatka)
    try:
        xls_path, txt_path, pdf_path = generuj_excel_zmiany(date.today())
    except Exception:
        xls_path = None; txt_path = None; pdf_path = None

    # 3. Spróbuj otworzyć Outlooka (jeśli dostępny) — nie przerywamy w przeciwnym wypadku
    try:
        if xls_path:
            otworz_outlook_z_raportem(xls_path, uwagi)
    except Exception:
        app.logger.exception('Outlook open failed')

    # 4. Jeśli pliki wygenerowane, zwracamy ZIP do pobrania (automatyczne pobranie plików przez przeglądarkę)
    if xls_path or txt_path or ('pdf_path' in locals() and pdf_path):
        from zipfile import ZipFile
        zip_name = f"Raport_{date.today()}.zip"
        zip_path = os.path.join('raporty', zip_name)
        try:
            with ZipFile(zip_path, 'w') as z:
                if xls_path and os.path.exists(xls_path):
                    z.write(xls_path, arcname=os.path.basename(xls_path))
                if txt_path and os.path.exists(txt_path):
                    z.write(txt_path, arcname=os.path.basename(txt_path))
                if 'pdf_path' in locals() and pdf_path and os.path.exists(pdf_path):
                    z.write(pdf_path, arcname=os.path.basename(pdf_path))
            return send_file(zip_path, as_attachment=True)
        except Exception:
            app.logger.exception('Failed to create/send zip')

    # Fallback: jeśli nic do pobrania, przekieruj na stronę logowania
    return redirect('/login')

@app.route('/wyslij_raport_email', methods=['POST'])
def wyslij_raport_email(): return redirect('/')

if __name__ == '__main__': print("🚀 Serwer wystartował: http://YOUR_IP_ADDRESS:8082"); serve(app, host='0.0.0.0', port=8082, threads=6)