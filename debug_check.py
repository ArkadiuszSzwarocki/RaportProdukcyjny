from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# Check Workowanie plans today
cursor.execute("""
    SELECT id, produkt, tonaz, status, sekcja, tonaz_rzeczywisty 
    FROM plan_produkcji 
    WHERE DATE(data_planu) = CURDATE() 
    AND sekcja = 'Workowanie' 
    AND is_deleted = 0 
    LIMIT 5
""")
plans = cursor.fetchall()
print('=== WORKOWANIE PLANS TODAY ===')
if plans:
    for p in plans:
        print(f'  ID {p[0]}: {p[1]} | Status: {p[3]} | Tonaz: {p[2]} | Rzeczywisty: {p[5]}')
else:
    print('  Brak planów!')

# Check szarża today
print()
cursor.execute("""
    SELECT id, plan_id, status, DATE(data_dodania), produkt 
    FROM szarze 
    WHERE DATE(data_dodania) = CURDATE() 
    LIMIT 10
""")
szarze = cursor.fetchall()
print('=== SZARŻA TODAY ===')
if szarze:
    for s in szarze:
        print(f'  Szarza ID {s[0]}: plan_id={s[1]}, status={s[2]}, produkt={s[4]}')
else:
    print('  Brak szarży!')

# Check Zasyp plans today
print()
cursor.execute("""
    SELECT id, produkt, tonaz, status
    FROM plan_produkcji 
    WHERE DATE(data_planu) = CURDATE() 
    AND sekcja = 'Zasyp'
    AND is_deleted = 0
    LIMIT 5
""")
zasyp = cursor.fetchall()
print('=== ZASYP PLANS TODAY ===')
if zasyp:
    for p in zasyp:
        print(f'  ID {p[0]}: {p[1]} | Status: {p[3]} | Tonaz: {p[2]}')
else:
    print('  Brak planów!')

cursor.close()
conn.close()
