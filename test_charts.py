from app.services.stats_service import get_chart_data, get_kpi_data
from datetime import date

# Test functions
d_od = date(2026, 2, 26)
d_do = date(2026, 2, 27)

try:
    print('[TEST] get_kpi_data...')
    kpi = get_kpi_data(d_od, d_do)
    print(f'  plan: {kpi.get("plan")}')
    print(f'  wykonanie: {kpi.get("wykonanie")}')
    
    print('[TEST] get_chart_data...')
    charts = get_chart_data(d_od, d_do)
    print(f'  labels type: {type(charts.get("labels"))}')
    print(f'  labels value: {charts.get("labels")}')
    print(f'  plan type: {type(charts.get("plan"))}')
    print(f'  plan value: {charts.get("plan")}')
    print(f'  pie_labels: {charts.get("pie_labels")}')
    print(f'  pie_values: {charts.get("pie_values")}')
    print('[OK] All functions work!')
except Exception as e:
    print(f'[ERROR] {e}')
    import traceback
    traceback.print_exc()
