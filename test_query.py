import sys
sys.path.insert(0, 'c:/Users/arkad/Documents/GitHub/RaportProdukcyjny')
from datetime import date
from app.utils.queries import QueryHelper

# Call the actual query function that dashboard uses

today = date.today()
plans = QueryHelper.get_plan_produkcji(today, 'Zasyp')
print(f"[*] Query results for {today}, sekcja='Zasyp':")
print(f"    Found {len(plans)} plans")
for p in plans:
    print(f"    ID={p[0]}, Produkt={p[1]}")

if len(plans) == 0:
    print("\n[!] Query returned no plans!")
    
    # Try case-insensitive directly
    plans2 = QueryHelper.get_plan_produkcji(today, 'zasyp')
    print(f"\n[*] Query results for {today}, sekcja='zasyp':")
    print(f"    Found {len(plans2)} plans")
    for p in plans2:
        print(f"    ID={p[0]}, Produkt={p[1]}")
