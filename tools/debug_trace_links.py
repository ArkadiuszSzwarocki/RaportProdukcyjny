import sys
sys.path.append('a:\\GitHub\\RaportProdukcyjny')
from app.core.database import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute("USE biblioteka")

# Find pallet
cursor.execute("SELECT id, nr_palety, plan_id, produkt FROM magazyn_palety_agro WHERE nr_palety = 'AGR000001783422245368'")
pal = cursor.fetchone()
print(f"Paleta: {pal}")

if pal and pal.get('plan_id'):
    plan_id = pal['plan_id']
    cursor.execute("SELECT id, sekcja, produkt, nr_receptury, zasyp_id FROM plan_produkcji_agro WHERE id = %s", (plan_id,))
    plan = cursor.fetchone()
    print(f"Plan workowania (id={plan_id}): {plan}")

    if plan and plan.get('zasyp_id'):
        zasyp_id = plan['zasyp_id']
        cursor.execute("SELECT id, sekcja, produkt, nr_receptury, status FROM plan_produkcji_agro WHERE id = %s", (zasyp_id,))
        zasyp = cursor.fetchone()
        print(f"Plan Zasyp (id={zasyp_id}): {zasyp}")

cursor.close()
conn.close()
