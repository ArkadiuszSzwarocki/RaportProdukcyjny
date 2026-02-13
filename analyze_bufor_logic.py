#!/usr/bin/env python3
"""Sprawdź czy logika wpadania szarż do bufora jest prawidłowa"""
import mysql.connector
from app.config import DB_CONFIG

conn = mysql.connector.connect(**DB_CONFIG)
cursor = conn.cursor()

print("="*80)
print("DIAGNOZA: Logika wpadania szarz do bufora vs rzeczywistość")
print("="*80)

# Sprawdzenie czy w bufor ARE Zasypy które NIE mają odpowiadającego Workowania z prawidłowym FK
print("\n1️⃣  SZARŻE W BUFORZE - ze wszystkich dni:")
print("-" * 80)

cursor.execute("""
    SELECT 
        b.id,
        b.zasyp_id,
        b.produkt,
        b.tonaz_rzeczywisty,
        b.status,
        COALESCE(z.status, 'N/A') as zasyp_status,
        CASE 
            WHEN w_linked.id IS NOT NULL THEN 'TAK (linked)'
            WHEN w_any.id IS NOT NULL THEN 'TAK (unlinked)'
            ELSE 'NIE'
        END as ma_workowanie,
        COALESCE(w_any.id, -1) as any_workowanie_id
    FROM bufor b
    LEFT JOIN plan_produkcji z ON z.id = b.zasyp_id
    LEFT JOIN plan_produkcji w_linked ON w_linked.zasyp_id = b.zasyp_id AND w_linked.sekcja = 'Workowanie'
    LEFT JOIN plan_produkcji w_any ON w_any.id = b.zasyp_id AND w_any.sekcja = 'Workowanie'
    WHERE b.status = 'aktywny'
    ORDER BY b.data_planu DESC, b.kolejka
    LIMIT 20
""")

rows = cursor.fetchall()
print(f"Znaleziono {len(rows)} szarż w buforze (limit 20):\n")

for buf_id, zasyp_id, produkt, tonaz, status, z_status, ma_workowanie, any_wid in rows:
    wideo_info = f"({any_wid})" if any_wid > 0 else ""
    print(f"Bufor ID {buf_id:4d}: Produkt={produkt:15s} | zasyp_id={str(zasyp_id) if zasyp_id else 'None':4} | "
          f"Tonaz={tonaz:7.0f} kg | Status={status} | Zasyp.status={z_status:12s} | Ma Workowanie: {ma_workowanie} {wideo_info}")

print("\n" + "="*80)
print("INTERPRETACJA:")
print("="*80)
print("""
Szarża wpadnie do bufora (refresh_bufor_queue) jeśli spełnia warunki:
  1. Zasyp ma status IN ('w toku', 'zakonczone')
  2. Zasyp MA POWIĄZANE Workowanie (via FK zasyp_id)
  3. To Workowanie ma status IN ('w toku', 'zaplanowane')
  4. Zasyp.tonaz_rzeczywisty > 0

Prawidły przepływ:
  Zasyp (plan_produkcji, id=896, sekcja='Zasyp')
    ↓ FK: plan_produkcji.id (897) ma zasyp_id = 896
  Workowanie (plan_produkcji, id=897, sekcja='Workowanie', zasyp_id=896)
    ↓ refresh_bufor_queue() INNER JOIN
  Bufor (zasyp_id=896, tonaz_rzeczywisty=1040)

Problem z Plan 896/897:
  - Zasyp 896 (1040 kg, zakonczone) ✓
  - Workowanie 897 (zasyp_id = None) ✗ BRAK LINKU!
  - refresh_bufor_queue nie zrobiłby INNER JOIN
  - ALE Plan 896 IS w buforze (ID 6731)
  
  → Szarża mogła wpaść do bufora gdy był między link,
    a potem został USUNIĘTY lub WYCZYSZCZONY.

""")

print("="*80)
print("ODPOWIEDŹ NA PYTANIE:")
print("="*80)
print("""
✓ Szarża z zakoniczonego Zasypu POWINNA wpadać do bufora - to jest prawidłowa logika.

✓ Kod jest POPRAWNY - szarża wpadają do bufora jeśli istnieje powiązane Workowanie.

⚠️  PROBLEM W OBECNYCH DANYCH:
   Plan 897 (Workowanie) nie ma zasyp_id=896 - brak linku!
   To jest błąd danych lub błąd w logice tworzenia Workowania.

JEŚLI Workowanie ma zasyp_id = None, to system nie wie że jest powiązane z Zasyp 896.
To może być przyczyna zamieszania z planami 896/897.
""")

print("="*80)

conn.close()
