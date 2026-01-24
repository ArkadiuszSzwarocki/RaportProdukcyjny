import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from db import get_db_connection
import pandas as pd

def list_products(date='2026-01-23'):
    conn = get_db_connection()
    df = pd.read_sql("SELECT produkt FROM plan_produkcji WHERE data_planu = %s", conn, params=(date,))
    conn.close()
    vals = df['produkt'].astype(str).tolist()
    counts = {}
    for v in vals:
        counts[v] = counts.get(v, 0) + 1
    for v, c in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
        print(repr(v), '=>', c)

if __name__ == '__main__':
    list_products()
