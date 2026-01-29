#!/usr/bin/env python3
"""Skrypt pomocniczy: zasiej obsadę i liderów dla podanej daty.

Użycie:
  python tools/seed_obsada.py --date 2026-01-29 \
      --assign Zasyp:12 --assign Workowanie:34 --lider-psd 12 --lider-agro 34

Wymaga skonfigurowanego połączenia w `config.DB_CONFIG` (używa `db.get_db_connection`).
"""
import argparse
from datetime import datetime, date
from db import get_db_connection


def parse_args():
    p = argparse.ArgumentParser(description='Seed obsada_zmiany and obsada_liderzy for a date')
    p.add_argument('--date', required=False, help='Data YYYY-MM-DD (domyślnie dzisiaj)')
    p.add_argument('--assign', action='append', help='Przypisanie w formacie Sekcja:pracownik_id (można powtórzyć)')
    p.add_argument('--lider-psd', type=int, help='ID lidera PSD')
    p.add_argument('--lider-agro', type=int, help='ID lidera AGRO')
    return p.parse_args()


def ensure_obsada_liderzy(conn, qdate, lider_psd, lider_agro):
    cur = conn.cursor()
    cur.execute("INSERT INTO obsada_liderzy (data_wpisu, lider_psd_id, lider_agro_id) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE lider_psd_id=VALUES(lider_psd_id), lider_agro_id=VALUES(lider_agro_id)", (qdate, lider_psd, lider_agro))


def add_obsada_entry(conn, qdate, sekcja, pracownik_id):
    cur = conn.cursor()
    # avoid duplicate exact same entry
    cur.execute("SELECT COUNT(1) FROM obsada_zmiany WHERE data_wpisu=%s AND sekcja=%s AND pracownik_id=%s", (qdate, sekcja, pracownik_id))
    if int(cur.fetchone()[0] or 0) > 0:
        print(f"[skip] istnieje: {sekcja} - {pracownik_id} dla {qdate}")
        return False
    cur.execute("INSERT INTO obsada_zmiany (data_wpisu, sekcja, pracownik_id) VALUES (%s, %s, %s)", (qdate, sekcja, pracownik_id))
    # ensure obecnosc exists
    try:
        cur.execute("SELECT COUNT(1) FROM obecnosc WHERE pracownik_id=%s AND data_wpisu=%s", (pracownik_id, qdate))
        if int(cur.fetchone()[0] or 0) == 0:
            cur.execute("INSERT INTO obecnosc (data_wpisu, pracownik_id, typ, ilosc_godzin, komentarz) VALUES (%s, %s, %s, %s, %s)", (qdate, pracownik_id, 'Obecność', 8, 'Automatyczne z obsady'))
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
    return True


def main():
    args = parse_args()
    if args.date:
        try:
            qdate = datetime.strptime(args.date, '%Y-%m-%d').date()
        except Exception:
            print('Błędny format daty, użyj YYYY-MM-DD')
            return
    else:
        qdate = date.today()

    assigns = []
    if args.assign:
        for a in args.assign:
            if ':' not in a:
                print('Nieprawidłowy format assign, oczekiwano Sekcja:pracownik_id ->', a)
                continue
            sekcja, pid = a.split(':', 1)
            try:
                pid = int(pid)
            except Exception:
                print('Nieprawidłowe id pracownika:', pid)
                continue
            assigns.append((sekcja.strip(), pid))

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        if args.lider_psd or args.lider_agro:
            ensure_obsada_liderzy(conn, qdate, args.lider_psd, args.lider_agro)
            print(f'Zapisano liderów dla {qdate}: PSD={args.lider_psd} AGRO={args.lider_agro}')

        inserted = 0
        for sekcja, pid in assigns:
            ok = add_obsada_entry(conn, qdate, sekcja, pid)
            if ok:
                inserted += 1

        conn.commit()
        print(f'Gotowe. Dodano {inserted} wpisów do obsady dla {qdate}').
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == '__main__':
    main()
