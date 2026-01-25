from db import get_db_connection
from datetime import date, timedelta

conn = get_db_connection()
c = conn.cursor()

try:
    # 1) Dodaj pracownika
    name = 'jupiter5'
    c.execute("INSERT INTO pracownicy (imie_nazwisko, grupa) VALUES (%s, %s)", (name, ''))
    conn.commit()
    c.execute("SELECT id FROM pracownicy WHERE imie_nazwisko=%s ORDER BY id DESC LIMIT 1", (name,))
    r = c.fetchone()
    pid = int(r[0]) if r else None
    print('Inserted pracownik id=', pid)

    # 2) Dodaj wniosek urlopowy na jutro (jednodniowy)
    tomorrow = date.today() + timedelta(days=1)
    c.execute("INSERT INTO wnioski_wolne (pracownik_id, typ, data_od, data_do, czas_od, czas_do, powod) VALUES (%s,%s,%s,%s,%s,%s,%s)", (pid, 'Urlop', tomorrow, tomorrow, None, None, 'Testowy urlop dla jupiter5'))
    conn.commit()
    c.execute("SELECT id, status, zlozono FROM wnioski_wolne WHERE pracownik_id=%s ORDER BY zlozono DESC LIMIT 1", (pid,))
    w = c.fetchone()
    print('Inserted wniosek:', w)

    # 3) Dopisz dzisiaj obsadę i obecność (dzień pracujący)
    today = date.today()
    # obsada_zmiany
    try:
        c.execute("INSERT INTO obsada_zmiany (data_wpisu, sekcja, pracownik_id) VALUES (%s, %s, %s)", (today, 'Zasyp', pid))
    except Exception:
        conn.rollback()
        print('Failed to insert obsada_zmiany (maybe duplicate)')
    # obecnosc
    try:
        c.execute("INSERT INTO obecnosc (data_wpisu, pracownik_id, typ, ilosc_godzin, komentarz) VALUES (%s,%s,%s,%s,%s)", (today, pid, 'Obecność', 8, 'Dopisano ręcznie przez skrypt'))
    except Exception:
        conn.rollback()
        print('Failed to insert obecnosc (maybe duplicate)')
    conn.commit()

    # 4) Wyniki - wyświetl kalendarz dla pracownika (dziś i jutro)
    print('\nObecnosc dziś:')
    c.execute("SELECT id, typ, ilosc_godzin, komentarz FROM obecnosc WHERE pracownik_id=%s AND data_wpisu=%s", (pid, today))
    print(c.fetchall())
    print('\nObsada dziś:')
    c.execute("SELECT id, sekcja FROM obsada_zmiany WHERE pracownik_id=%s AND data_wpisu=%s", (pid, today))
    print(c.fetchall())
    print('\nWnioski obejmujace jutro:')
    c.execute("SELECT id, typ, data_od, data_do, status FROM wnioski_wolne WHERE pracownik_id=%s AND data_od <= %s AND data_do >= %s", (pid, tomorrow, tomorrow))
    print(c.fetchall())

finally:
    try:
        conn.close()
    except Exception:
        pass
