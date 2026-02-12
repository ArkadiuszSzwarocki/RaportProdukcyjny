from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

print('='*100)
print('REKOMENDACJA POPRAWY DANYCH AGRO MILK TOP')
print('='*100)

# PLAN 625: 3000 kg
# Szarze: 3440 kg (nadmiar 440 kg)
# Czy zmniejszać szarze czy zwiększać plan?
# Jeśli szarze to faktyczne dane, to plan powinien być 3440

# PLAN 890: 10000 kg
# Szarze: 10778 kg (nadmiar 778 kg)
# Jeśli szarze to faktyczne dane, to plan powinien być 10778

# PLAN 882: 1680 kg BUFOR
# Szarze: 1 kg (BRAKUJE 1679 kg!)
# To jest WYRAŹNY BUG

print('\n[1] PLAN 625 - AGRO MILK TOP (3000 kg)')
print('  Szarze: 3440 kg (nadmiar 440 kg)')
print('  OPCJA: Zmienić plan na 3440 kg')
print('  RATIONALE: Szarze to rzeczywiste dane wprowadzane')

print('\n[2] PLAN 890 - AGRO MILK TOP (10000 kg)')
print('  Szarze: 10778 kg (nadmiar 778 kg)')
print('  OPCJA: Zmienić plan na 10778 kg')
print('  RATIONALE: Szarze to rzeczywiste dane wprowadzane')

print('\n[3] PLAN 882 - AGRO MILK TOP - BUFOR (1680 kg) **KRITYCZNA**')
print('  Szarze: 1 kg (BRAKUJE 1679 kg!) **BUG**')
print('  OPCJA: Zmienić szarze z 1 kg na 1680 kg')
print('  RATIONALE: Widoczny błąd - być może pomyłka przy wpisywaniu')

print()
print('='*100)
print('AKTUALNIE: Czy użytkownik prosił aby poprawić na podstawie szarż czy palet?')
print('='*100)

# Sprawdz czy palety_workowanie ma jakiekolwiek dane
cursor.execute('SELECT COUNT(*) FROM palety_workowanie')
count_work = cursor.fetchone()[0]
print(f'Palety_workowanie - wszystkie wpisy: {count_work}')

# Sprawdz statystyki szarze
cursor.execute('SELECT COUNT(*) FROM szarze')
count_szarze = cursor.fetchone()[0]
cursor.execute('SELECT SUM(waga) FROM szarze')
sum_szarze = cursor.fetchone()[0]
print(f'Szarze - wszystkie wpisy: {count_szarze}, suma: {sum_szarze} kg')

# Sprawdz czy jest jakiś pattern - może szarze zawiera dane które mają być w workowanie?
print()
print('SZCZEGOL SZARZE DLA TYCH PLANOW:')
cursor.execute('''
    SELECT s.id, s.plan_id, s.waga, s.status, p.produkt, COUNT(*) OVER (PARTITION BY s.plan_id) as cnt
    FROM szarze s
    JOIN plan_produkcji p ON s.plan_id = p.id
    WHERE s.plan_id IN (625, 890, 882)
    ORDER BY s.plan_id, s.id
''')
for row in cursor.fetchall():
    print(f'  Szarze ID {row[0]:3d} (Plan {row[1]:3d}): {row[2]:8.1f} kg, Status: {row[3]:15s}, Plan: {row[4]} (total: {row[5]})')

cursor.close()
conn.close()
