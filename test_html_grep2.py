with open('templates/magazyn_dostawy/przyjecie_ruchu.html', 'r', encoding='utf-8') as f:
    for i, line in enumerate(f):
        if 'data_produkcji' in line or 'data-produkcji' in line or 'expiryDate' in line or 'productionDate' in line:
            print(f"{i+1}: {line.strip()}")
