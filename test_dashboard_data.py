from app.services.dashboard_service import DashboardService
from datetime import date

print("=" * 70)
print("TEST: Dane w dashboard_global")
print("=" * 70)

dzisiaj = date.today()
plans_zasyp, plans_workowanie = DashboardService.get_full_plans_for_sections(dzisiaj)

print(f"\n[Zasyp]\nIlosc planów: {len(plans_zasyp)}")
if plans_zasyp:
    print(f"Liczba kolumn: {len(plans_zasyp[0])}")
    for i, p in enumerate(plans_zasyp[:2]):
        print(f"  Plan {i+1} (ID={p[0]}): produkt={p[1]}, uszkodzone_worki=p[11]={p[11]}")

print(f"\n[Workowanie]\nIlosc planów: {len(plans_workowanie)}")
if plans_workowanie:
    print(f"Liczba kolumn: {len(plans_workowanie[0])}")
    for i, p in enumerate(plans_workowanie[:2]):
        print(f"  Plan {i+1} (ID={p[0]}): produkt={p[1]}, uszkodzone_worki=p[11]={p[11]}")

print("\n✓ Dane powinny teraz wyświetlać się prawidłowo w dashboard!")
