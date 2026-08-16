from app.db import get_db_connection
from datetime import date, datetime

conn = get_db_connection()
cur = conn.cursor()

try:
    # Create a temp Workowanie plan
    today = date.today()
    produkt = 'TEST_REPRO'
    cur.execute("INSERT INTO plan_produkcji (data_planu, sekcja, produkt, tonaz, status, kolejnosc, typ_produkcji) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (today, 'Workowanie', produkt, 0, 'zaplanowane', 9999, 'test'))
    plan_id = cur.lastrowid
    print('Created plan id', plan_id)

    # Insert paleta with waga = 1 (Workowanie)
    cur.execute("INSERT INTO palety_workowanie (plan_id, waga, tara, waga_brutto, data_dodania, status) VALUES (%s,%s,%s,%s,NOW(),%s)",
                (plan_id, 1, 25, 0, 'do_przyjecia'))
    paleta_id = cur.lastrowid
    conn.commit()
    print('Inserted paleta id', paleta_id)

    # Show current paleta
    cur.execute('SELECT id, plan_id, waga, waga_potwierdzona, waga_brutto, status FROM palety_workowanie WHERE id=%s', (paleta_id,))
    print('Before confirm:', cur.fetchone())

    # Simulate confirmation with provided netto = 5
    provided_netto = 5
    provided_brutto = provided_netto + 25

    cur.execute('UPDATE palety_workowanie SET waga_potwierdzona=%s WHERE id=%s', (provided_netto, paleta_id))
    cur.execute('UPDATE palety_workowanie SET waga_brutto=%s WHERE id=%s', (provided_brutto, paleta_id))
    cur.execute("UPDATE palety_workowanie SET status='przyjeta', data_potwierdzenia=NOW() WHERE id=%s", (paleta_id,))

    # Also mimic plan_produkcji Magazyn aggregate update (best-effort)
    cur.execute('SELECT data_planu, produkt FROM plan_produkcji WHERE id=%s', (plan_id,))
    row = cur.fetchone()
    if row:
        cur.execute("UPDATE plan_produkcji SET tonaz_rzeczywisty = COALESCE(tonaz_rzeczywisty,0) + %s WHERE data_planu=%s AND produkt=%s AND sekcja='Magazyn'",
                    (provided_netto, row[0], row[1]))

    conn.commit()

    cur.execute('SELECT id, plan_id, waga, waga_potwierdzona, waga_brutto, status FROM palety_workowanie WHERE id=%s', (paleta_id,))
    print('After confirm:', cur.fetchone())

finally:
    try:
        cur.close()
    except Exception:
        pass
    try:
        conn.close()
    except Exception:
        pass
