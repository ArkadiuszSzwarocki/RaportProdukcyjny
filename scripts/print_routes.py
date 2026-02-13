from app.core.factory import create_app

if __name__ == '__main__':
    app = create_app(init_db=False)
    rules = sorted(app.url_map.iter_rules(), key=lambda r: (r.rule, list(r.methods)))
    for r in rules:
        print(f"{r.rule} -> {sorted(r.methods)}")
