from app.db import get_db_connection, refresh_bufor_queue
from datetime import datetime

PRODUCT = 'AGRO MILK TOP'
DATE = '2026-03-17'
SZARZA_KG = 1000

conn = None
try:
    conn = get_db_connection()
    cursor = conn.cursor()

    # Find Zasyp plan
    cursor.execute("SELECT id, tonaz, tonaz_rzeczywisty, status FROM plan_produkcji WHERE DATE(data_planu) = %s AND produkt = %s AND sekcja = 'Zasyp' ORDER BY id DESC LIMIT 1", (DATE, PRODUCT))
    zas = cursor.fetchone()
    if not zas:
        print(f'No Zasyp plan found for {PRODUCT} on {DATE}')
    else:
        zas_id = zas[0]
        print('Found Zasyp:', zas)

        now = datetime.now()
        godz = now.strftime('%H:%M:%S')
        # Insert szarza
        cursor.execute("INSERT INTO szarze (plan_id, waga, data_dodania, godzina, pracownik_id, status) VALUES (%s, %s, %s, %s, %s, %s)",
                       (zas_id, SZARZA_KG, now, godz, None, 'zarejestowana'))
        # Update plan tonaz_rzeczywisty
        cursor.execute("UPDATE plan_produkcji SET tonaz_rzeczywisty = COALESCE((SELECT SUM(waga) FROM szarze WHERE plan_id = %s), 0) + COALESCE((SELECT SUM(kg) FROM dosypki WHERE plan_id = %s AND potwierdzone = 1 AND COALESCE(anulowana,0)=0),0) WHERE id = %s", (zas_id, zas_id, zas_id))
        conn.commit()
        print(f'Inserted szarza {SZARZA_KG}kg for zasyp_id={zas_id}')

        # Now print plan_produkcji rows for date/product
        cursor.execute("SELECT id, sekcja, produkt, tonaz, tonaz_rzeczywisty, status FROM plan_produkcji WHERE DATE(data_planu)=%s AND produkt=%s ORDER BY sekcja, id", (DATE, PRODUCT))
        rows = cursor.fetchall()
        print('\nplan_produkcji rows:')
        for r in rows:
            print(r)

        # Print palety_workowanie
        cursor.execute("SELECT id, plan_id, waga, status FROM palety_workowanie WHERE plan_id IN (SELECT id FROM plan_produkcji WHERE DATE(data_planu)=%s AND produkt=%s AND sekcja='Workowanie') ORDER BY id", (DATE, PRODUCT))
        pws = cursor.fetchall()
        print('\npalety_workowanie rows:')
        for p in pws:
            print(p)

        # Refresh buffer and print bufor rows
        try:
            refresh_bufor_queue(conn)
        except Exception as e:
            print('refresh_bufor_queue failed:', e)

        cursor.execute("SELECT id, zasyp_id, produkt, tonaz_rzeczywisty, spakowano, kolejka FROM bufor WHERE DATE(data_planu)=%s AND produkt=%s ORDER BY kolejka", (DATE, PRODUCT))
        bufor = cursor.fetchall()
        print('\nbufor rows:')
        for b in bufor:
            print(b)

except Exception as e:
    print('ERROR:', e)
finally:
    try:
        if conn:
            conn.close()
    except Exception:
        pass
