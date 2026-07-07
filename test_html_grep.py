with open('templates/magazyn_dostawy/przyjecie_ruchu.html', 'r', encoding='utf-8') as f:
    for i, line in enumerate(f):
        if 'window.open' in line or 'location.href' in line or 'report_url' in line or 'raport-przesuniecia' in line:
            print(f"{i+1}: {line.strip()}")
