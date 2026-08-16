import codecs

filepath = 'a:/GitHub/RaportProdukcyjny/app/blueprints/warehouse/routes/palety_routes.py'
with codecs.open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace("from .printing_routes import _async_print_label, _select_preferred_printer", "from .printing_routes import _select_preferred_printer")

with codecs.open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
print("Fixed palety_routes.py")
