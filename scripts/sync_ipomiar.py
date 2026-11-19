"""Dedicated read-only collector CLI. Web requests only read its atomic archives."""
import argparse
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv(override=False)

from app.services.ipomiar_collector_service import collect_day  # noqa: E402
from app.services.ipomiar_service import ZONE, day_string, devices  # noqa: E402


def collect(day, config):
    return collect_day(day, config)


def main():
    parser = argparse.ArgumentParser(description='Archive iPomiar readings for AGRO')
    parser.add_argument('--date', help='YYYY-MM-DD; defaults to today and yesterday')
    parser.add_argument('--watch', action='store_true', help='Refresh every 60 seconds')
    args = parser.parse_args()
    while True:
        today = datetime.now(ZONE).date()
        days = [day_string(args.date)] if args.date else [str(today), str(today - timedelta(days=1))]
        failed = False
        configured = devices()
        if not configured:
            print('No devices configured', flush=True)
            return 1
        for config in configured:
            for day in days:
                try:
                    print(f'{day}: {config["name"]}: archived {collect(day, config)} measurements', flush=True)
                except Exception as error:
                    # Do not log device keys, response bodies or exception URLs.
                    print(f'{day}: {config["name"]}: readings unavailable ({type(error).__name__}); archive preserved', flush=True)
                    failed = True
        if not args.watch:
            return int(failed)
        time.sleep(60)


if __name__ == '__main__':
    raise SystemExit(main())
