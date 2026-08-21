import ast
import codecs

routes_path = 'a:/GitHub/RaportProdukcyjny/app/blueprints/warehouse/routes/palety_routes.py'
service_path = 'a:/GitHub/RaportProdukcyjny/app/services/warehouse_pallet_service.py'

with codecs.open(routes_path, 'r', encoding='utf-8') as f:
    source = f.read()

lines = source.splitlines()
tree = ast.parse(source)

# We want to extract dodaj_palete, edytuj_palete, usun_palete, potwierdz_palete body to service.
# Wait, let's just create the service file manually for dodaj_palete first to see how it looks.
