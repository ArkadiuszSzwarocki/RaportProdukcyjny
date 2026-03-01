#!/usr/bin/env python
from app.core.factory import create_app

app = create_app()

# Print all registered routes
print("\n=== Registered Routes ===")
for rule in app.url_map.iter_rules():
    if 'wnioski' in rule.rule:
        print(f"{rule.rule:50} {rule.methods} -> {rule.endpoint}")
