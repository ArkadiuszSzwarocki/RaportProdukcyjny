#!/usr/bin/env python3
from app.services.planning_service import PlanningService
from app.db import get_db_connection
from app.core.factory import create_app

# Ensure we have Flask application context for logging/current_app usage
app = create_app()
import json

def dump_plans_for_date(date_str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, sekcja, produkt, tonaz, tonaz_rzeczywisty, status, zasyp_id FROM plan_produkcji WHERE DATE(data_planu) = %s ORDER BY id", (date_str,))
    rows = cur.fetchall()
    print(f"\n--- plan_produkcji for {date_str}: {len(rows)} rows")
    for r in rows:
        print(r)
    cur.execute("SELECT id, zasyp_id, data_planu, produkt, tonaz_rzeczywisty, spakowano, kolejka, status FROM bufor WHERE data_planu = %s ORDER BY id", (date_str,))
    rows = cur.fetchall()
    print(f"\n--- bufor for {date_str}: {len(rows)} rows")
    for r in rows:
        print(r)
    conn.close()

if __name__ == '__main__':
    source_date = '2026-03-16'
    print('Calling PlanningService.przenies_niezrealizowane for', source_date)
    with app.app_context():
        res = PlanningService.przenies_niezrealizowane(source_date)
        print('\nResult:', res)
        dump_plans_for_date('2026-03-17')
