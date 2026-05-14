import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.services.mom_service import MomService

plans = MomService.get_open_plans()
print(f"Open plans without MOM: {len(plans)}")
for p in plans[:5]:
    print(f"  #{p['id']} {p['data_planu']} {p['produkt']} ({p['status']})")

# Test: open MOM for plan #25
mom_id = MomService.open_mom(25)
print(f"\nCreated MOM id={mom_id}")

mom = MomService.get_mom(mom_id)
print(f"MOM #{mom['id']} plan={mom['plan_id']} produkt={mom['produkt']} status={mom['status']}")
print(f"  tonaz_plan={mom['tonaz_planowany']} tonaz_rz={mom['tonaz_rzeczywisty']}")
print(f"  pozycje ({len(mom['pozycje'])}):")
for poz in mom['pozycje']:
    print(f"    {poz['surowiec_nazwa']}: przesunieto={poz['przesunieto_kg']} zuzycie={poz['zuzycie_kg']} roznica={poz['roznica_kg']}")

moms = MomService.list_moms(limit=5)
print(f"\nExisting MOMs: {len(moms)}")
for m in moms:
    print(f"  MOM#{m['id']} plan={m['plan_id']} {m['produkt']} status={m['status']}")
