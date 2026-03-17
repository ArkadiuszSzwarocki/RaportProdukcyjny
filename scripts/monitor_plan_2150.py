import time
import json
from app.db import get_db_connection
from datetime import datetime

PLAN_ZASYP = 2150
PLAN_WORKOWANIE = 2151
POLL_INTERVAL = 3


def fetch_state():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT id, data_planu, sekcja, produkt, tonaz, tonaz_rzeczywisty, status FROM plan_produkcji WHERE id IN (%s,%s)", (PLAN_ZASYP, PLAN_WORKOWANIE))
    plans = {r[0]: {'data_planu': str(r[1]), 'sekcja': r[2], 'produkt': r[3], 'tonaz': float(r[4]) if r[4] is not None else None, 'tonaz_rzeczywisty': float(r[5]) if r[5] is not None else None, 'status': r[6]} for r in cur.fetchall()}

    cur.execute("SELECT id, waga, data_dodania FROM szarze WHERE plan_id=%s ORDER BY id", (PLAN_ZASYP,))
    szarze = [{'id': r[0], 'waga': float(r[1]), 'data_dodania': str(r[2])} for r in cur.fetchall()]

    cur.execute("SELECT id, plan_id, waga, tara, data_dodania FROM palety_workowanie WHERE plan_id IN (%s,%s) ORDER BY id", (PLAN_ZASYP, PLAN_WORKOWANIE))
    palety = [{'id': r[0], 'plan_id': r[1], 'waga': float(r[2]) if r[2] is not None else 0.0, 'tara': float(r[3]) if r[3] is not None else 0.0, 'data_dodania': str(r[4])} for r in cur.fetchall()]

    cur.execute("SELECT id, action, changes, user_login, created_at FROM plan_history WHERE plan_id IN (%s,%s) ORDER BY id DESC LIMIT 20", (PLAN_ZASYP, PLAN_WORKOWANIE))
    history = [{'id': r[0], 'action': r[1], 'changes': r[2], 'user_login': r[3], 'created_at': str(r[4])} for r in cur.fetchall()]

    conn.close()
    return {'plans': plans, 'szarze': szarze, 'palety': palety, 'history': history}


def main():
    prev = None
    print(f"[{datetime.now()}] Monitor started for plans {PLAN_ZASYP}/{PLAN_WORKOWANIE}. Poll interval {POLL_INTERVAL}s. Stop with Ctrl+C or kill python process.")
    try:
        while True:
            state = fetch_state()
            ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            if prev is None:
                print(f"[{ts}] Initial state:\n" + json.dumps(state, ensure_ascii=False, indent=2))
            else:
                # detect changes
                if state['plans'] != prev['plans']:
                    print(f"[{ts}] Plans changed:\n" + json.dumps(state['plans'], ensure_ascii=False, indent=2))
                if state['szarze'] != prev['szarze']:
                    print(f"[{ts}] Szarze changed (count {len(state['szarze'])}):\n" + json.dumps(state['szarze'], ensure_ascii=False, indent=2))
                if state['palety'] != prev['palety']:
                    print(f"[{ts}] Palety changed (count {len(state['palety'])}):\n" + json.dumps(state['palety'], ensure_ascii=False, indent=2))
                if state['history'] != prev['history']:
                    print(f"[{ts}] History changed (latest):\n" + json.dumps(state['history'][:5], ensure_ascii=False, indent=2))
            prev = state
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print('Monitor stopped by user')


if __name__ == '__main__':
    main()
