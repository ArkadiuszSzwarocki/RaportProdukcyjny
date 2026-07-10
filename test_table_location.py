from app.db import get_db_connection

conn = get_db_connection()
cur = conn.cursor(dictionary=True)

codes = ['PSD020320262455411041', 'AGR000001782288263514']

print('=' * 70)
print('SPRAWDZENIE GDZIE SĄ KODY W BAZIE')
print('=' * 70)

for code in codes:
    print(f'\n🔍 Kod: {code}')
    
    # magazyn_palety_agro
    cur.execute('SELECT id, produkt, waga_netto, lokalizacja FROM magazyn_palety_agro WHERE nr_palety = %s', (code,))
    agro = cur.fetchone()
    if agro:
        print(f'   ✅ magazyn_palety_agro: id={agro["id"]}, {agro["produkt"]}, {agro["waga_netto"]}kg @ {agro["lokalizacja"]}')
    else:
        print('   ❌ magazyn_palety_agro: BRAK')
    
    # palety_agro
    cur.execute('SELECT id, waga, status FROM palety_agro WHERE nr_palety = %s', (code,))
    agro_unconf = cur.fetchone()
    if agro_unconf:
        print(f'   ⏳ palety_agro: id={agro_unconf["id"]}, status={agro_unconf["status"]}, {agro_unconf["waga"]}kg')
    else:
        print('   ❌ palety_agro: BRAK')
    
    # magazyn_palety_workowanie (PSD)
    try:
        cur.execute('SELECT id, produkt, waga_netto, lokalizacja FROM magazyn_palety_psd WHERE nr_palety = %s', (code,))
        psd = cur.fetchone()
        if psd:
            print(f'   ✅ magazyn_palety_psd: id={psd["id"]}, {psd["produkt"]}, {psd["waga_netto"]}kg @ {psd["lokalizacja"]}')
        else:
            print('   ❌ magazyn_palety_psd: BRAK')
    except Exception as e:
        print(f'   ⚠️  magazyn_palety_psd: {e}')
    
    # palety_workowanie (PSD)
    try:
        cur.execute('SELECT id, waga, status FROM palety_workowanie WHERE nr_palety = %s', (code,))
        psd_unconf = cur.fetchone()
        if psd_unconf:
            print(f'   ⏳ palety_workowanie: id={psd_unconf["id"]}, status={psd_unconf["status"]}, {psd_unconf["waga"]}kg')
        else:
            print('   ❌ palety_workowanie: BRAK')
    except Exception as e:
        print(f'   ⚠️  palety_workowanie: {e}')

conn.close()

print('\n' + '=' * 70)
print('WNIOSEK:')
print('=' * 70)
print('Jeśli kod PSD jest tylko w magazyn_palety_agro,')
print('to skaner PSD go NIE ZNAJDZIE (bo szuka w magazyn_palety_psd).')
print()
print('Jeśli kod AGR jest tylko w magazyn_palety_agro,')
print('to skaner AGRO go ZNAJDZIE.')
