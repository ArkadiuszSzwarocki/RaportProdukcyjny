"""
Prosty skrypt do przenoszenia niezrealizowanych zleceń.
Uruchamiać codziennie o 06:00 (Windows Task Scheduler / cron).

Przykład wywołania ręcznego:
python scripts/rollover.py
python scripts/rollover.py --from 2025-01-17 --to 2025-01-18
"""
from datetime import date, timedelta
import argparse

# Gdy skrypt jest uruchamiany przez Task Scheduler, CWD może być inny.
# Dodajemy katalog projektu do `sys.path`, aby importy typu `from db import ...`
# działały niezależnie od working directory.
import sys
from pathlib import Path
project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Upewnij się, że ścieżka projektu jest w PYTHONPATH gdy uruchamiasz skrypt
from db import rollover_unfinished


def main():
    parser = argparse.ArgumentParser(description='Rollover niezrealizowanych zleceń')
    parser.add_argument('--from', dest='from_date', help='Data źródłowa (YYYY-MM-DD)')
    parser.add_argument('--to', dest='to_date', help='Data docelowa (YYYY-MM-DD)')
    args = parser.parse_args()

    if args.from_date and args.to_date:
        from_date = args.from_date
        to_date = args.to_date
    else:
        today = date.today()
        from_date = (today - timedelta(days=1)).isoformat()
        to_date = today.isoformat()

    print(f"Rollover: {from_date} -> {to_date}")
    added = rollover_unfinished(from_date, to_date)
    print(f"Dodano {added} zleceń.")


if __name__ == '__main__':
    main()
