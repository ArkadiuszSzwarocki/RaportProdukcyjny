#!/usr/bin/env python3
"""Cleanup duplicates in obsada_zmiany and obecnosc.

Usage:
  python tools/cleanup_obsada.py --dry-run
  python tools/cleanup_obsada.py         # will ask for confirmation
  python tools/cleanup_obsada.py --yes   # run without prompt

This script uses `db.get_db_connection()` from the project to connect.
Make a DB backup before running.
"""
import argparse
from db import get_db_connection


DELETE_OBSADA = """
DELETE o1
FROM obsada_zmiany o1
JOIN (
  SELECT MIN(id) AS keep_id, pracownik_id, data_wpisu, sekcja
  FROM obsada_zmiany
  GROUP BY pracownik_id, data_wpisu, sekcja
  HAVING COUNT(*) > 1
) dup ON o1.pracownik_id = dup.pracownik_id
    AND o1.data_wpisu = dup.data_wpisu
    AND o1.sekcja = dup.sekcja
    AND o1.id <> dup.keep_id;
"""

DELETE_OBECNOSC = """
DELETE o1
FROM obecnosc o1
JOIN (
  SELECT MIN(id) AS keep_id, pracownik_id, data_wpisu, komentarz
  FROM obecnosc
  WHERE komentarz = 'Automatyczne z obsady'
  GROUP BY pracownik_id, data_wpisu, komentarz
  HAVING COUNT(*) > 1
) dup ON o1.pracownik_id = dup.pracownik_id
    AND o1.data_wpisu = dup.data_wpisu
    AND COALESCE(o1.komentarz,'') = COALESCE(dup.komentarz,'')
    AND o1.id <> dup.keep_id;
"""


def parse_args():
    p = argparse.ArgumentParser(description='Cleanup duplicate obsada/obecnosc rows')
    p.add_argument('--dry-run', action='store_true', help='Only show counts and examples, do not delete')
    p.add_argument('--yes', action='store_true', help='Run without confirmation')
    return p.parse_args()


def count_duplicates(conn):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM (SELECT pracownik_id, data_wpisu, sekcja, COUNT(*) as cnt FROM obsada_zmiany GROUP BY pracownik_id, data_wpisu, sekcja HAVING cnt>1) x")
    dup_obs = int(cur.fetchone()[0] or 0)
    cur.execute("SELECT COUNT(*) FROM (SELECT pracownik_id, data_wpisu, komentarz, COUNT(*) as cnt FROM obecnosc WHERE komentarz='Automatyczne z obsady' GROUP BY pracownik_id, data_wpisu, komentarz HAVING cnt>1) x")
    dup_obec = int(cur.fetchone()[0] or 0)
    return dup_obs, dup_obec


def show_examples(conn):
    cur = conn.cursor()
    print('\nPrzykładowe powielone wpisy w obsada_zmiany:')
    cur.execute('''SELECT pracownik_id, data_wpisu, sekcja, COUNT(*) as cnt FROM obsada_zmiany GROUP BY pracownik_id, data_wpisu, sekcja HAVING cnt>1 LIMIT 10''')
    for r in cur.fetchall():
        print(r)
    print('\nPrzykładowe powielone wpisy w obecnosc:')
    cur.execute('''SELECT pracownik_id, data_wpisu, komentarz, COUNT(*) as cnt FROM obecnosc WHERE komentarz='Automatyczne z obsady' GROUP BY pracownik_id, data_wpisu, komentarz HAVING cnt>1 LIMIT 10''')
    for r in cur.fetchall():
        print(r)


def run_cleanup(conn):
    cur = conn.cursor()
    print('Wykonuję usuwanie duplikatów z tabeli obsada_zmiany...')
    cur.execute(DELETE_OBSADA)
    print('Affected (obsada_zmiany):', cur.rowcount)
    print('Wykonuję usuwanie duplikatów z tabeli obecnosc...')
    cur.execute(DELETE_OBECNOSC)
    print('Affected (obecnosc):', cur.rowcount)
    conn.commit()


def main():
    args = parse_args()
    conn = get_db_connection()
    try:
        dup_obs, dup_obec = count_duplicates(conn)
        print(f'Znaleziono {dup_obs} powielonych grup w obsada_zmiany, {dup_obec} w obecnosc (auto)')
        show_examples(conn)
        if args.dry_run:
            print('\nDry-run: koniec. Nie wykonano usuwania.')
            return
        if not args.yes:
            ok = input('\nCzy na pewno chcesz usunąć powyższe duplikaty? (tak/nie): ').strip().lower()
            if ok not in ('tak', 'y', 'yes'):
                print('Anulowano.')
                return
        run_cleanup(conn)
        print('Cleanup wykonany pomyślnie.')
    finally:
        try: conn.close()
        except Exception: pass


if __name__ == '__main__':
    main()
