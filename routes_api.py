from flask import Blueprint, request, redirect, url_for, flash, render_template, session
import os
from datetime import date, datetime
from contextlib import contextmanager

from db import get_db_connection
from decorators import login_required, zarzad_required


api_bp = Blueprint('api', __name__)


# Pomocniczy context manager dla pracy z kursorem DB
@contextmanager
def db_cursor(commit: bool = False):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        yield cur
        if commit:
            conn.commit()
    finally:
        conn.close()


@api_bp.route('/dodaj_plan', methods=['POST'])
@login_required
def dodaj_plan():
    sekcja = request.form.get('sekcja', 'Zasyp')
    data_planu = request.form.get('data_planu')
    produkt = request.form.get('produkt')
    tonaz = request.form.get('tonaz')

    with db_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO plan_produkcji (data_planu, produkt, tonaz, status, sekcja) VALUES (%s, %s, %s, 'zaplanowane', %s)",
            (data_planu, produkt, tonaz, sekcja),
        )

    return redirect(url_for('index', sekcja=sekcja, data=data_planu))


@api_bp.route('/usun_plan/<int:id>', methods=['POST'])
@login_required
def usun_plan(id):
    # KROK 2: Zabezpieczenie - upewniamy się, że ID to na pewno liczba
    try:
        id = int(id)
    except ValueError:
        return "Błąd: Nieprawidłowe ID", 400

    data_powrotu = request.form.get('data_powrotu', date.today())
    with db_cursor(commit=True) as cur:
        # Tu jest drugie zabezpieczenie: użycie %s zamiast f-stringa
        cur.execute("DELETE FROM plan_produkcji WHERE id=%s", (id,))

    return redirect(url_for('index', sekcja='Zasyp', data=data_powrotu))


@api_bp.route('/start_zlecenie/<int:id>', methods=['POST'])
@login_required
def start_zlecenie(id):
    sekcja_arg = request.args.get('sekcja', 'Zasyp')
    data_powrotu = request.form.get('data_powrotu', date.today())

    # Pobierz dane zlecenia, zaktualizuj statusy i ewentualnie dodaj zadanie Workowanie
    with db_cursor(commit=True) as cur:
        cur.execute("SELECT produkt, tonaz, sekcja, data_planu FROM plan_produkcji WHERE id=%s", (id,))
        z = cur.fetchone()

        cur.execute(
            "UPDATE plan_produkcji SET status='zakonczone', real_stop=NOW() WHERE status='w toku' AND id!=%s AND sekcja=(SELECT sekcja FROM plan_produkcji WHERE id=%s)",
            (id, id),
        )

        cur.execute("UPDATE plan_produkcji SET status='w toku', real_start=NOW() WHERE id=%s", (id,))

        if z and z[2] == 'Zasyp':
            cur.execute(
                "SELECT id FROM plan_produkcji WHERE data_planu=%s AND produkt=%s AND tonaz=%s AND sekcja='Workowanie'",
                (z[3], z[0], z[1]),
            )
            if not cur.fetchone():
                cur.execute(
                    "INSERT INTO plan_produkcji (data_planu, sekcja, produkt, tonaz, status) VALUES (%s, 'Workowanie', %s, %s, 'zaplanowane')",
                    (z[3], z[0], z[1]),
                )

    return redirect(url_for('index', sekcja=sekcja_arg, data=data_powrotu))


@api_bp.route('/koniec_zlecenie/<int:id>', methods=['POST'])
@login_required
def koniec_zlecenie(id):
    sekcja_arg = request.args.get('sekcja', 'Zasyp')
    data_powrotu = request.form.get('data_powrotu', date.today())

    with db_cursor(commit=True) as cur:
        cur.execute("UPDATE plan_produkcji SET status='zakonczone', real_stop=NOW() WHERE id=%s", (id,))

    return redirect(url_for('index', sekcja=sekcja_arg, data=data_powrotu))


@api_bp.route('/start_przejscie', methods=['POST'])
@login_required
def start_przejscie():
    data_powrotu = request.form.get('data_powrotu', date.today())
    with db_cursor(commit=True) as cur:
        cur.execute("UPDATE plan_produkcji SET status='zakonczone', real_stop=NOW() WHERE status='w toku'")
        cur.execute(
            "INSERT INTO plan_produkcji (data_planu, produkt, tonaz, status, real_start) VALUES (%s, 'PRZEJŚCIE / ZMIANA', 0, 'w toku', NOW())",
            (data_powrotu,),
        )

    return redirect(url_for('index', sekcja='Zasyp', data=data_powrotu))


@api_bp.route('/zapisz_tonaz/<int:id>', methods=['POST'])
@login_required
def zapisz_tonaz(id):
    data_powrotu = request.form.get('data_powrotu', date.today())
    tonaz_val = request.form.get('tonaz_rzeczywisty')
    tonaz = tonaz_val.replace(',', '.') if tonaz_val else None

    with db_cursor(commit=True) as cur:
        cur.execute("UPDATE plan_produkcji SET tonaz_rzeczywisty=%s WHERE id=%s", (tonaz, id))

    return redirect(url_for('index', sekcja='Zasyp', data=data_powrotu))


@api_bp.route('/dodaj_palete/<int:plan_id>', methods=['POST'])
@login_required
def dodaj_palete(plan_id):
    data_powrotu = request.form.get('data_powrotu')
    waga_raw = request.form.get('waga_palety', '0').replace(',', '.')
    waga = float(waga_raw)

    with db_cursor(commit=True) as cur:
        cur.execute("INSERT INTO palety_workowanie (plan_id, waga) VALUES (%s, %s)", (plan_id, waga))
        cur.execute(
            "UPDATE plan_produkcji SET tonaz_rzeczywisty = (SELECT SUM(waga) / 1000 FROM palety_workowanie WHERE plan_id = %s) WHERE id = %s",
            (plan_id, plan_id),
        )

    return redirect(url_for('index', sekcja='Workowanie', data=data_powrotu))


@api_bp.route('/cofnij_palete/<int:plan_id>', methods=['POST'])
@login_required
def cofnij_palete(plan_id):
    data_powrotu = request.form.get('data_powrotu')
    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM palety_workowanie WHERE plan_id=%s ORDER BY id DESC LIMIT 1", (plan_id,))
        cur.execute(
            "UPDATE plan_produkcji SET tonaz_rzeczywisty = COALESCE((SELECT SUM(waga) / 1000 FROM palety_workowanie WHERE plan_id = %s), 0) WHERE id = %s",
            (plan_id, plan_id),
        )

    return redirect(url_for('index', sekcja='Workowanie', data=data_powrotu))


@api_bp.route('/dodaj_obecnosc', methods=['POST'])
@login_required
def dodaj_obecnosc():
    typ = request.form.get('typ')
    komentarz = request.form.get('komentarz', '').strip()
    if typ == 'Nadgodziny' and not komentarz:
        flash("BŁĄD: Wymagany powód nadgodzin!", "error")
        return redirect(url_for('index') + '#panel-lidera')

    data_wpisu = request.form.get('data_wpisu', date.today())
    pracownik_id = request.form.get('pracownik_id')
    godziny = request.form.get('godziny', 0)

    with db_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO obecnosc (data_wpisu, pracownik_id, typ, ilosc_godzin, komentarz) VALUES (%s, %s, %s, %s, %s)",
            (data_wpisu, pracownik_id, typ, godziny, komentarz),
        )

    return redirect(url_for('index') + '#panel-lidera')


@api_bp.route('/usun_obecnosc/<int:id>', methods=['POST'])
@login_required
def usun_obecnosc(id):
    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM obecnosc WHERE id=%s", (id,))

    return redirect(url_for('index') + '#panel-lidera')


@api_bp.route('/dodaj_do_obsady', methods=['POST'])
@login_required
def dodaj_do_obsady():
    sekcja = request.form.get('sekcja')
    pracownik_id = request.form.get('pracownik_id')

    with db_cursor(commit=True) as cur:
        cur.execute("INSERT INTO obsada_zmiany (data_wpisu, sekcja, pracownik_id) VALUES (%s, %s, %s)", (date.today(), sekcja, pracownik_id))

    return redirect(url_for('index', sekcja=sekcja))


@api_bp.route('/usun_z_obsady/<int:id>', methods=['POST'])
@login_required
def usun_z_obsady(id):
    sekcja = request.form.get('sekcja')
    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM obsada_zmiany WHERE id = %s", (id,))

    return redirect(url_for('index', sekcja=sekcja))


@api_bp.route('/dodaj_wpis', methods=['POST'])
@login_required
def dodaj_wpis():
    sekcja = request.form.get('sekcja')
    problem = request.form.get('problem')
    czas_start = request.form.get('czas_start') or datetime.now().strftime("%H:%M")
    kategoria = request.form.get('kategoria')

    with db_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO dziennik_zmiany (data_wpisu, sekcja, problem, czas_start, status, kategoria) VALUES (%s, %s, %s, %s, 'roboczy', %s)",
            (date.today(), sekcja, problem, czas_start, kategoria),
        )

    return redirect(url_for('index', sekcja=sekcja))


@api_bp.route('/usun_wpis/<int:id>', methods=['POST'])
@login_required
def usun_wpis(id):
    sekcja = request.form.get('sekcja')
    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM dziennik_zmiany WHERE id = %s", (id,))

    return redirect(url_for('index', sekcja=sekcja))


@api_bp.route('/edytuj/<int:id>', methods=['GET', 'POST'])
@login_required
def edytuj(id):
    if request.method == 'POST':
        problem = request.form.get('problem')
        kategoria = request.form.get('kategoria')
        czas_start = request.form.get('czas_start') or None
        czas_stop = request.form.get('czas_stop') or None

        with db_cursor(commit=True) as cur:
            cur.execute(
                "UPDATE dziennik_zmiany SET problem=%s, kategoria=%s, czas_start=%s, czas_stop=%s WHERE id=%s",
                (problem, kategoria, czas_start, czas_stop, id),
            )

        return redirect('/')

    with db_cursor() as cur:
        cur.execute("SELECT * FROM dziennik_zmiany WHERE id = %s", (id,))
        wpis = cur.fetchone()

    return render_template('edycja.html', wpis=wpis)


@api_bp.route('/manual_rollover', methods=['POST'])
@login_required
def manual_rollover():
    """Przenosi (move) niezakończone zlecenia z jednej daty na inną.

    Logika: najpierw tworzymy brakujące wpisy na datę docelową, następnie usuwamy
    oryginalne niezakończone wpisy z daty źródłowej.
    """
    from_date = request.form.get('from_date')
    to_date = request.form.get('to_date')
    if not from_date or not to_date:
        flash('Brak wymaganych dat.', 'error')
        return redirect(url_for('zarzad_panel'))

    # uprawnienia: tylko planista lub lider
    if session.get('rola') not in ['planista', 'lider']:
        flash('Brak uprawnień do wykonania tej operacji.', 'error')
        return redirect(url_for('zarzad_panel'))

    try:
        with db_cursor(commit=True) as cur:
            # Wstaw brakujące rekordy na datę docelową
            cur.execute(
                """
                INSERT INTO plan_produkcji (data_planu, sekcja, produkt, tonaz, status)
                SELECT %s, p.sekcja, p.produkt, p.tonaz, 'zaplanowane'
                FROM plan_produkcji p
                WHERE p.data_planu = %s AND COALESCE(p.status, '') != 'zakonczone'
                  AND NOT EXISTS (
                    SELECT 1 FROM plan_produkcji p2
                    WHERE p2.data_planu = %s
                      AND p2.sekcja = p.sekcja
                      AND p2.produkt = p.produkt
                      AND (p2.tonaz = p.tonaz OR (p2.tonaz IS NULL AND p.tonaz IS NULL))
                  )
                """,
                (to_date, from_date, to_date),
            )

            inserted = cur.rowcount

            # Usuń oryginalne, niezakończone rekordy na from_date
            cur.execute(
                "DELETE FROM plan_produkcji WHERE data_planu = %s AND COALESCE(status, '') != 'zakonczone'",
                (from_date,),
            )
            deleted = cur.rowcount

        # Logowanie wyniku do pliku dla diagnostyki
        try:
            logs_dir = os.path.join(os.getcwd(), 'logs')
            os.makedirs(logs_dir, exist_ok=True)
            with open(os.path.join(logs_dir, 'manual_rollover.log'), 'a', encoding='utf-8') as lf:
                lf.write(f"[{datetime.now().isoformat()}] manual_rollover from={from_date} to={to_date} inserted={inserted} deleted={deleted}\n")
        except Exception:
            pass

        flash(f'Przeniesiono {deleted} zleceń (dodano {inserted}).', 'success')
    except Exception as e:
        try:
            logs_dir = os.path.join(os.getcwd(), 'logs')
            os.makedirs(logs_dir, exist_ok=True)
            with open(os.path.join(logs_dir, 'manual_rollover.log'), 'a', encoding='utf-8') as lf:
                lf.write(f"[{datetime.now().isoformat()}] manual_rollover ERROR from={from_date} to={to_date} err={e}\n")
        except Exception:
            pass
        flash(f'Błąd podczas przenoszenia: {e}', 'error')

    return redirect(url_for('zarzad_panel'))
# W routes_api.py - Aktualizacja dodaj_plan i nowe endpointy

@api_bp.route('/dodaj_plan_zaawansowany', methods=['POST'])
@login_required
def dodaj_plan_zaawansowany():
    if session.get('rola') not in ['planista', 'admin']:
        return redirect('/')

    sekcja = request.form.get('sekcja')
    data_planu = request.form.get('data_planu')
    produkt = request.form.get('produkt')
    tonaz = request.form.get('tonaz')
    # Checkbox w HTML zwraca 'on' jeśli zaznaczony, lub None
    wymaga_oplaty = request.form.get('wymaga_oplaty') 
    
    status = 'nieoplacone' if wymaga_oplaty else 'zaplanowane'

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO plan_produkcji (data_planu, produkt, tonaz, status, sekcja) VALUES (%s, %s, %s, %s, %s)",
        (data_planu, produkt, tonaz, status, sekcja)
    )
    conn.commit()
    conn.close()

    return redirect(url_for('planista.panel_planisty', data=data_planu))

@api_bp.route('/zmien_status_zlecenia/<int:id>', methods=['POST'])
@login_required
def zmien_status_zlecenia(id):
    nowy_status = request.form.get('status')
    data_powrotu = request.form.get('data_powrotu')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE plan_produkcji SET status=%s WHERE id=%s", (nowy_status, id))
    conn.commit()
    conn.close()
    
    return redirect(url_for('planista.panel_planisty', data=data_powrotu))

@api_bp.route('/przenies_zlecenie/<int:id>', methods=['POST'])
@login_required
def przenies_zlecenie(id):
    nowa_data = request.form.get('nowa_data')
    stara_data = request.form.get('stara_data') # do powrotu
    
    if nowa_data:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE plan_produkcji SET data_planu=%s WHERE id=%s", (nowa_data, id))
        conn.commit()
        conn.close()
    
    return redirect(url_for('planista.panel_planisty', data=stara_data))