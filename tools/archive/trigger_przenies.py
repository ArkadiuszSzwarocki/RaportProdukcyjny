"""Trigger przenies_niezrealizowane from CLI for testing.

Usage:
  python tools/trigger_przenies.py 2026-03-29

If no date provided, uses today's date.
"""
import sys
from app.core.factory import create_app
from app.services.planning.buffer import PlanningBufferService

def main(date_arg=None):
  """Run przenies_niezrealizowane for given date (YYYY-MM-DD). If date_arg is None uses today."""
  app = create_app()
  with app.app_context():
    if not date_arg:
      from datetime import date
      date_arg = date.today().isoformat()
    print(f"Triggering przenies_niezrealizowane for date: {date_arg}")
    success, message, count = PlanningBufferService.przenies_niezrealizowane(date_arg)
    print('RESULT:')
    print('success=', success)
    print('message=', message)
    print('count=', count)
    return (0 if success else 2)


if __name__ == '__main__':
  date_arg = sys.argv[1] if len(sys.argv) > 1 else None
  exit_code = main(date_arg)
  sys.exit(exit_code)
