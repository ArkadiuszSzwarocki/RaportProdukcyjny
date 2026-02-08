from datetime import date
from app.services.dashboard_service import DashboardService

d = date.today()
print('DATE:', d)
print('\nactive_products:')
print(DashboardService.get_active_products(d))
print('\nbuffer_queue:')
print(DashboardService.get_buffer_queue(d))
print('\nwork_first_map:')
print(DashboardService.get_first_workowanie_map(d))
print('\nzasyp_product_order:')
zpo = DashboardService.get_zasyp_product_order(d)
print(zpo)

allowed = set()
orders = {prod: zpo.get(prod, 999999) for prod in DashboardService.get_first_workowanie_map(d).keys()}
if orders:
    min_order = min(orders.values())
    for prod, ordv in orders.items():
        if ordv == min_order:
            allowed.add(DashboardService.get_first_workowanie_map(d).get(prod))
print('\nallowed_work_start_ids:')
print(allowed)

print('\nWorkowanie plans from get_production_plans:')
plans, pal, sp, sw = DashboardService.get_production_plans(d, 'Workowanie')
for p in plans:
    # print id, product, status, kolejnosc, repr of product
    prod = p[1] if len(p)>1 else None
    print('id=', p[0], 'prod=', repr(prod), 'status=', p[3], 'kolejnosc=', (p[8] if len(p)>8 else None))

print('\nBuffer map keys repr:')
for k in DashboardService.get_buffer_queue(d).keys():
    print(repr(k))

print('\nWork_first_map keys repr:')
for k in DashboardService.get_first_workowanie_map(d).keys():
    print(repr(k))
