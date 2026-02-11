import sys
import os
from datetime import date

# Ensure repository root is on sys.path so `app` package can be imported
repo_root = os.path.dirname(os.path.dirname(__file__))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from app.services.dashboard_service import DashboardService


def print_plans_for_section(section):
    print('\n' + '='*60)
    print(f"Sekcja: {section} - data: {date.today().isoformat()}")
    try:
        plans, palety_map, suma_plan, suma_wykonanie = DashboardService.get_production_plans(date.today(), section)
    except Exception as e:
        print(f"Błąd podczas pobierania planów dla {section}: {e}")
        return

    if not plans:
        print('Brak planów')
        return

    print(f"Suma plan: {suma_plan} | Suma wykonanie (liczona): {suma_wykonanie}")
    print('-'*60)
    for p in plans:
        # Ensure indices
        plan_id = p[0] if len(p) > 0 else None
        produkt = p[1] if len(p) > 1 else ''
        tonaz_plan = p[2] if len(p) > 2 else 0
        status = p[3] if len(p) > 3 else ''
        real_start = p[4] if len(p) > 4 else ''
        real_stop = p[5] if len(p) > 5 else ''
        tonaz_rzeczywisty = p[7] if len(p) > 7 else 0
        szarze_count = p[15] if len(p) > 15 else None
        print(f"ID={plan_id:4} | Produkt={produkt:20s} | Plan={tonaz_plan:8} | Wykonanie={tonaz_rzeczywisty:8} | Szarze/Palety={szarze_count} | Status={status}")


if __name__ == '__main__':
    print_plans_for_section('Zasyp')
    print_plans_for_section('Workowanie')
