import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from generator_raportow import generuj_paczke_raportow
import traceback, sys

if __name__ == '__main__':
    data = '2026-01-23'
    try:
        xls, txt, pdf = generuj_paczke_raportow(data, 'test uwagi')
        print('OK:')
        print('XLS:', xls)
        print('TXT:', txt)
        print('PDF:', pdf)
    except Exception as e:
        print('EXCEPTION:')
        traceback.print_exc()
        sys.exit(1)
