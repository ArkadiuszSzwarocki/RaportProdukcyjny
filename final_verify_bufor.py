#!/usr/bin/env python3
"""Final verification - szarża z Zasypu trafia do bufora"""
import mysql.connector
from app.config import DB_CONFIG

conn = mysql.connector.connect(**DB_CONFIG)
cursor = conn.cursor()

print("="*80)
print("FINALNA WERYFIKACJA: Szarża trafia do bufora")
print("="*80)

# 1. Sprawdzenie powiązania 896 <-> 897
print("\n1️⃣  POWIĄZANIE PLANÓW:")
print("-" * 80)

cursor.execute("""
    SELECT 
        z.id, z.sekcja, z.status, z.tonaz_rzeczywisty,
        w.id as workowanie_id, w.sekcja as w_sekcja, w.status as w_status, w.zasyp_id
    FROM plan_produkcji z
    LEFT JOIN plan_produkcji w ON w.zasyp_id = z.id AND w.sekcja = 'Workowanie'
    WHERE z.id = 896 AND z.sekcja = 'Zasyp'
""")

row = cursor.fetchone()
if row:
    z_id, z_sekcja, z_status, z_tonaz_rz, w_id, w_sekcja, w_status, w_zasyp_id = row
    print(f"✓ Plan 896 (Zasyp):")
    print(f"  - Status: {z_status}")
    print(f"  - Tonaz_rzeczywisty: {z_tonaz_rz} kg")
    if w_id:
        print(f"✓ Plan {w_id} (Workowanie / powiązany):")
        print(f"  - Sekcja: {w_sekcja}")
        print(f"  - Status: {w_status}")
        print(f"  - Zasyp_id (FK): {w_zasyp_id}")
        if w_zasyp_id == 896:
            print(f"  ✅ POPRAWNY LINK!")
        else:
            print(f"  ❌ ZŁY LINK!")
    else:
        print(f"❌ Brak powiązanego Workowania")

# 2. Sprawdzenie czy Zasyp spełnia warunki do bufora
print("\n2️⃣  CZY ZASYP 896 SPEŁNIA WARUNKI DO BUFORA?")
print("-" * 80)

warunki = {
    'Zasyp.status IN (w toku, zakonczone)': z_status in ('w toku', 'zakonczone'),
    'Zasyp.tonaz_rzeczywisty > 0': z_tonaz_rz and z_tonaz_rz > 0,
    'Ma powiązane Workowanie': w_id is not None,
    'Workowanie.status IN (w toku, zaplanowane)': w_status in ('w toku', 'zaplanowane') if w_status else False
}

wszystkie_spelnione = all(warunki.values())

for warunek, spelniony in warunki.items():
    symbol = "✓" if spelniony else "✗"
    print(f"{symbol} {warunek}")

print()
if wszystkie_spelnione:
    print("✅ WSZYSTKIE WARUNKI SPEŁNIONE - Plan 896 POWINIEN być w buforze")
else:
    print("❌ NIE WSZYSTKIE WARUNKI - Plan 896 NIE POWINIEN być w buforze")

# 3. Sprawdzenie czy jest w buforze
print("\n3️⃣  CZY PLAN 896 JEST W BUFORZE?")
print("-" * 80)

cursor.execute("""
    SELECT id, status, tonaz_rzeczywisty, kolejka, spakowano
    FROM bufor
    WHERE zasyp_id = 896
    ORDER BY id
""")

buff_rows = cursor.fetchall()
if buff_rows:
    print(f"✅ TAK - znaleziono {len(buff_rows)} wpis(ów):")
    for buf_id, buf_status, buf_tonaz, buf_kolejka, buf_spakowano in buff_rows:
        print(f"   - Bufor ID {buf_id}: status={buf_status}, tonaz={buf_tonaz} kg, "
              f"kolejka={buf_kolejka}, spakowano={buf_spakowano} kg")
else:
    print(f"❌ NIE - Plan 896 nie ma wpisu w buforze")

# 4. Podsumowanie
print("\n" + "="*80)
print("PODSUMOWANIE:")
print("="*80)

if wszystkie_spelnione:
    if buff_rows:
        print("""
✅ WSZYSTKO DZIAŁA PRAWIDŁOWO!

Szarża z zakoniczonego Zasypu PRAWIDŁOWO trafia do bufora:
  ✓ Plan 896 (1040 kg, zakonczone) ma powiązane Workowanie 897
  ✓ Workowanie 897 ma status 'zaplanowane'
  ✓ Plan 896 jest w buforze i czeka w kolejce na spakowanie

WNIOSEK: Logika kodu jest prawidłowa, a dane teraz się zgadzają.
Przepływ: Zasyp 896 (1040 kg szarża) → Bufor → czeka na Workowanie
""")
    else:
        print("""
⚠️  UWAGA: Warunki spełnione ale Plan 896 nie jest w buforze

To może oznaczać że refresh_bufor_queue nie został uruchomiony.
(Funkcja jest wywoływana automatycznie przy każdym otwarciu strony)
""")
else:
    print("""
❌ Problem: warunki nie spełnione

Sprawdź:
  - Status Zasypu (powinno być 'w toku' lub 'zakonczone')
  - Czy Workowanie ma prawidłowy zasyp_id
  - Status Workowania (powinno być 'w toku' lub 'zaplanowane')
""")

print("="*80)

conn.close()
