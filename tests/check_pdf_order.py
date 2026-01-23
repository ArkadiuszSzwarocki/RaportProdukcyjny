import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from generator_raportow import generuj_paczke_raportow

DATE = '2026-01-23'

if __name__ == '__main__':
    xls, txt, pdf = generuj_paczke_raportow(DATE, 'test-order')
    print('Generated PDF:', pdf)
    if not pdf:
        print('No PDF generated')
        sys.exit(1)
    path = pdf if os.path.isabs(pdf) else os.path.join(os.getcwd(), pdf)
    if not os.path.exists(path):
        print('PDF file missing at', path)
        sys.exit(1)
    data = open(path, 'rb').read()
    try:
        s = data.decode('latin-1')
    except Exception:
        s = str(data)
    names = []
    for name in ['Zasyp', 'Workowanie', 'Magazyn']:
        idxs = [i for i in range(len(s)) if s.startswith(name, i)]
        for i in idxs:
            names.append((i, name))
    names.sort()
    seq = [n for _, n in names]
    print('Sections found in PDF in order:')
    print(seq)

    # Basic validation: Workowanie should not appear before first Zasyp, Magazyn should not appear before first Zasyp
    try:
        first_z = seq.index('Zasyp') if 'Zasyp' in seq else None
    except ValueError:
        first_z = None
    problems = []
    for i, v in enumerate(seq):
        if v == 'Workowanie' and first_z is not None and i < first_z:
            problems.append(f'Workowanie before Zasyp at position {i}')
        if v == 'Magazyn' and first_z is not None and i < first_z:
            problems.append(f'Magazyn before Zasyp at position {i}')
    if problems:
        print('PROBLEMS:')
        for p in problems:
            print('-', p)
        sys.exit(2)
    else:
        print('Basic ordering checks passed.')
