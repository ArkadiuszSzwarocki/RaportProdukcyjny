from db import get_db_connection
from datetime import date

conn = get_db_connection()
cur = conn.cursor()

# 1) Ensure at least one worker exists
cur.execute("SELECT id, imie_nazwisko FROM pracownicy LIMIT 1")
row = cur.fetchone()
if not row:
    cur.execute("INSERT INTO pracownicy (imie_nazwisko) VALUES (%s)", ("Testowy Pracownik",))
    conn.commit()
    cur.execute("SELECT id, imie_nazwisko FROM pracownicy LIMIT 1")
    row = cur.fetchone()

pid = row[0]
name = row[1]
print(f"Using pracownik id={pid}, name={name}")

# 2) Insert into obsada_zmiany for today and sekcja 'Hala Agro'
today = date.today()
sekcja = 'Hala Agro'
cur.execute("SELECT COUNT(1) FROM obsada_zmiany WHERE data_wpisu=%s AND sekcja=%s AND pracownik_id=%s", (today, sekcja, pid))
exists = cur.fetchone()[0]
if not exists:
    cur.execute("INSERT INTO obsada_zmiany (data_wpisu, sekcja, pracownik_id) VALUES (%s, %s, %s)", (today, sekcja, pid))
    conn.commit()
    print("Inserted obsada_zmiany row")
else:
    print("Obsada entry already exists")

# 3) Print all obsada_zmiany for today
cur.execute("SELECT oz.id, oz.sekcja, p.imie_nazwisko FROM obsada_zmiany oz JOIN pracownicy p ON oz.pracownik_id=p.id WHERE oz.data_wpisu=%s ORDER BY oz.sekcja, p.imie_nazwisko", (today,))
rows = cur.fetchall()
print("Current obsada for today:")
for r in rows:
    print(r)

conn.close()

# 4) Generate reports via generator_raportow
try:
    from generator_raportow import generuj_paczke_raportow
    date_str = today.strftime('%Y-%m-%d')
    xls, txt, pdf = generuj_paczke_raportow(date_str, 'Automatyczny test uwag', 'Testowy Lider')
    print('Generator returned:')
    print('XLS:', xls)
    print('TXT:', txt)
    print('PDF:', pdf)
except Exception as e:
    print('Generator failed:', e)
    import traceback
    traceback.print_exc()
