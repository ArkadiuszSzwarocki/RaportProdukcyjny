import mysql.connector
import sys
import re
from datetime import datetime
from jinja2 import Environment, FileSystemLoader

sys.path.append('.')
from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)

# Fetch plan 72 details
cursor.execute("""
    SELECT w.id as work_id, w.produkt, w.tonaz_rzeczywisty as w_kg, 
           z.id as zasyp_id, z.tonaz_rzeczywisty as z_kg,
           w.nazwa_zlecenia, w.typ_produkcji
    FROM plan_produkcji_agro w
    LEFT JOIN plan_produkcji_agro z ON w.zasyp_id = z.id
    WHERE w.id = 72
""")
p = cursor.fetchone()

cursor.execute("""
    SELECT id, opakowanie_nazwa, stan_przed, wyprodukowano_szt, szt_na_palecie, zuzyte_worki, stan_po, autor_login, created_at
    FROM agro_workowanie_rozliczenie
    WHERE plan_id = %s
    ORDER BY created_at ASC
""", (p['work_id'],))
rozliczenia = cursor.fetchall()

cursor.execute("""
    SELECT ap.id, o.nazwa as opakowanie_nazwa, ap.stan_poczatkowy as stan_przed, ap.created_at
    FROM agro_plan_opakowania ap
    JOIN magazyn_opakowania o ON ap.opakowanie_id = o.id
    WHERE ap.plan_id = %s AND ap.is_active = TRUE
    ORDER BY ap.created_at ASC
""", (p['work_id'],))
aktywne_opakowania = cursor.fetchall()

cursor.execute("""
    SELECT 
        p.id, p.waga, p.status, p.data_dodania, 
        p.dodal_login,
        COALESCE(m.user_login, p.potwierdzil_login) as potwierdzil_login,
        COALESCE(m.data_potwierdzenia, p.data_potwierdzenia) as data_potwierdzenia
    FROM palety_agro p
    LEFT JOIN magazyn_palety_agro m ON p.id = m.paleta_workowanie_id
    WHERE p.plan_id = %s
    ORDER BY p.data_dodania ASC
""", (p['work_id'],))
pallets_raw = cursor.fetchall()

# Determine bag weight dynamically from typ_produkcji
bag_kg = 25.0
typ_prod = p.get('typ_produkcji') or ''
kg_match = re.search(r'(\d+)', typ_prod)
if kg_match:
    bag_kg = float(kg_match.group(1))

# Query packaging stocks
packaging_stocks = {}
unique_names = set()
for op in rozliczenia:
    if op.get('opakowanie_nazwa'):
        unique_names.add(op['opakowanie_nazwa'])
for aop in aktywne_opakowania:
    if aop.get('opakowanie_nazwa'):
        unique_names.add(aop['opakowanie_nazwa'])

for name in unique_names:
    cursor.execute("""
        SELECT COALESCE(SUM(stan_magazynowy), 0) as total_stock 
        FROM magazyn_opakowania 
        WHERE nazwa = %s AND (lokalizacja != 'ZUŻYTE' OR lokalizacja IS NULL)
    """, (name,))
    stock_row = cursor.fetchone()
    packaging_stocks[name] = float(stock_row['total_stock']) if stock_row else 0.0

report_data = []
report_data.append({
    'plan': p,
    'palety': pallets_raw,
    'mixes': [],
    'opakowania': rozliczenia,
    'aktywne_opakowania': aktywne_opakowania,
    'bag_kg': bag_kg,
    'packaging_stocks': packaging_stocks,
    'total_pallet_kg': sum(pal['waga'] or 0 for pal in pallets_raw),
    'total_mix_kg': 0
})

env = Environment(loader=FileSystemLoader('templates'))
# add format filters
#env.filters['format'] = lambda value, fmt: fmt % value

template = env.get_template('agro_warehouse/raport_palet.html')
class MockRequest:
    args = {}

rendered = template.render(
    report_data=report_data,
    data_planu="2026-05-30",
    single_view=True,
    is_ajax=False,
    session={},
    request=MockRequest(),
    print_date=datetime.now().strftime('%d.%m.%Y %H:%M')
)

# Find Podsumowanie Bilansu section in rendered HTML
for line in rendered.split('\n'):
    if 'Teoretyczne zużycie worków' in line or 'kg/worek' in line or 'Różnica / Strata' in line:
        print(line.strip())

conn.close()
