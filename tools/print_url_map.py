from app.core.factory import create_app

app = create_app(init_db=False)
for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
    methods = ','.join(sorted(rule.methods))
    print(f"{rule.rule:50} -> {rule.endpoint:40} [{methods}]")

# Try to find preprint specifically
print('\nFilter for /magazyn-dostawy/preprint:')
for rule in app.url_map.iter_rules():
    if 'preprint' in rule.rule:
        print(rule.rule, rule.endpoint, sorted(rule.methods))
