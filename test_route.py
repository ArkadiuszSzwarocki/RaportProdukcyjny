with open('app/blueprints/magazyn_dostawy/routes/transfer.py', 'r', encoding='utf-8') as f:
    for line in f:
        if 'reception_form' in line or 'przyjecie' in line or 'przyjmij' in line:
            print(line.strip())
