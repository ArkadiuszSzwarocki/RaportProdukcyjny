from app.services.scanner_service import ScannerService
from app.db import get_db_connection

code_agr = 'AGR000001782288263514'
code_psd = 'PSD020320262455411041'

print('=' * 70)
print('SZCZEGÓŁOWA DIAGNOZA')
print('=' * 70)

# Sprawdź w bazie
conn = get_db_connection()
cur = conn.cursor(dictionary=True)

print('\n📊 BAZA DANYCH - magazyn_palety_agro:')
cur.execute('SELECT id, nr_palety, produkt, waga_netto, lokalizacja FROM magazyn_palety_agro WHERE nr_palety IN (%s, %s)', (code_agr, code_psd))
for row in cur.fetchall():
    print(f'   ✅ {row["nr_palety"]}: {row["produkt"]} @ {row["lokalizacja"]} ({row["waga_netto"]} kg)')

print('\n📊 BAZA DANYCH - palety_agro:')
cur.execute('SELECT id, nr_palety, waga, status FROM palety_agro WHERE nr_palety IN (%s, %s)', (code_agr, code_psd))
for row in cur.fetchall():
    print(f'   ⏳ {row["nr_palety"]}: status={row["status"]} ({row["waga"]} kg)')

conn.close()

# Test lookup
print('\n🔍 SCANNER LOOKUP TEST:')

print(f'\n1️⃣ AGR (linia AGRO):')
result_agr = ScannerService.lookup_by_location(code_agr, 'AGRO')
if result_agr:
    print(f'   ✅ ZNALEZIONO')
    print(f'   Nazwa: {result_agr["nazwa"]}')
    print(f'   Typ: {result_agr["inventory_type"]}')
    print(f'   Lokalizacja: {result_agr["lokalizacja"]}')
    print(f'   is_unconfirmed_wg: {result_agr.get("is_unconfirmed_wg", False)}')
else:
    print('   ❌ NIE ZNALEZIONO')

print(f'\n2️⃣ PSD (linia PSD):')
result_psd = ScannerService.lookup_by_location(code_psd, 'PSD')
if result_psd:
    print(f'   ✅ ZNALEZIONO')
    print(f'   Nazwa: {result_psd["nazwa"]}')
    print(f'   Typ: {result_psd["inventory_type"]}')
    print(f'   Lokalizacja: {result_psd["lokalizacja"]}')
    print(f'   is_unconfirmed_wg: {result_psd.get("is_unconfirmed_wg", False)}')
else:
    print('   ❌ NIE ZNALEZIONO')

print(f'\n3️⃣ PSD z linią AGRO (błędna linia):')
result_psd_agro = ScannerService.lookup_by_location(code_psd, 'AGRO')
if result_psd_agro:
    print(f'   ✅ ZNALEZIONO (nie powinno!)')
    print(f'   Nazwa: {result_psd_agro["nazwa"]}')
else:
    print('   ❌ NIE ZNALEZIONO (poprawnie)')
