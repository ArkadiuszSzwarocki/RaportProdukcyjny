"""
Cleanup script: naprawia zduplikowane plany i błędny bufor po 3x kliknięciu 'Przenieś'.

Stan przed:
  - Plan 1428 (09.03, Zasyp, zakonczone, tonaz_rz=1190) — oryginał, poprawny
  - Plan 1429 (09.03, Workowanie, zaplanowane) — para oryginału
  - Plan 1430 (10.03, Zasyp, tonaz=3810, tonaz_rz=0) — 1. przeniesienie, jest OK
  - Plan 1431 (10.03, Workowanie, tonaz=1190) — para 1430
  - Plan 1432 (10.03, Zasyp duplikat) — usunąć
  - Plan 1433 (10.03, Workowanie duplikat) — usunąć
  - Plan 1434 (10.03, Zasyp duplikat) — usunąć
  - Plan 1435 (10.03, Workowanie duplikat) — usunąć
  - Bufor 98865 (09.03, zasyp_id=1428, tonaz_rz=1190) — przenieść/zaktualizować
  - Bufor 98860 (10.03, zasyp_id=1430, tonaz_rz=0) — naprawić: zmień zasyp_id=1428, tonaz_rz=1190
  - Bufor 98862 (10.03, zasyp_id=1432) — usunąć duplikat
  - Bufor 98864 (10.03, zasyp_id=1434) — usunąć duplikat

Stan po:
  - Bufor 98860 (10.03, zasyp_id=1428, tonaz_rz=1190) — poprawny, refresh_bufor_queue odczyta 1190 z planu 1428
  - Bufor 98865 na 09.03 usunięty — refresh nie odtworzy go, bo zasyp_id=1428 ma już entry na 10.03
"""
from app.db import get_db_connection

conn = get_db_connection()
cur = conn.cursor(dictionary=True)
diag_cur = conn.cursor()

print("=== PRZED CLEANUP ===")
diag_cur.execute("SELECT id, zasyp_id, data_planu, produkt, tonaz_rzeczywisty FROM bufor WHERE id IN (98860,98862,98864,98865)")
for r in diag_cur.fetchall(): print("BUFOR:", r)
diag_cur.execute("SELECT id, data_planu, sekcja, produkt, tonaz, tonaz_rzeczywisty FROM plan_produkcji WHERE id IN (1430,1431,1432,1433,1434,1435)")
for r in diag_cur.fetchall(): print("PLAN:", r)

print("\n=== USUWANIE ZDUPLIKOWANYCH BUFORÓW ===")
diag_cur.execute("DELETE FROM bufor WHERE id IN (98862, 98864)")
print(f"Deleted bufor duplikaty: {diag_cur.rowcount} rows")

print("\n=== USUWANIE ZDUPLIKOWANYCH PLANÓW ===")
diag_cur.execute("DELETE FROM plan_produkcji WHERE id IN (1432, 1433, 1434, 1435)")
print(f"Deleted plan duplikaty: {diag_cur.rowcount} rows")

print("\n=== NAPRAWA BUFORA 98860: zasyp_id=1428, tonaz_rz=1190 ===")
diag_cur.execute("UPDATE bufor SET zasyp_id=1428, tonaz_rzeczywisty=1190 WHERE id=98860")
print(f"Updated bufor 98860: {diag_cur.rowcount} rows")

print("\n=== USUWANIE STAREGO BUFORA 09.03 (98865) ===")
diag_cur.execute("DELETE FROM bufor WHERE id=98865")
print(f"Deleted bufor 98865 (09.03): {diag_cur.rowcount} rows")

conn.commit()
print("\n=== COMMIT ===")

print("\n=== PO CLEANUP ===")
diag_cur.execute("SELECT id, zasyp_id, data_planu, produkt, tonaz_rzeczywisty, kolejka, status FROM bufor WHERE DATE(data_planu) IN ('2026-03-09','2026-03-10') ORDER BY data_planu")
for r in diag_cur.fetchall(): print("BUFOR:", r)
diag_cur.execute("SELECT id, data_planu, sekcja, produkt, tonaz, tonaz_rzeczywisty FROM plan_produkcji WHERE id IN (1428,1429,1430,1431)")
for r in diag_cur.fetchall(): print("PLAN:", r)

conn.close()
print("\nDone.")
