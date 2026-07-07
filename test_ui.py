with open('app/blueprints/magazyn_dostawy/routes/ui.py', 'r', encoding='utf-8') as f:
    for line in f:
        if 'edycja_dostawy' in line or 'request.args.get' in line:
            print(line.strip())
