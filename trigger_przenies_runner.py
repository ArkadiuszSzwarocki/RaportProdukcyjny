"""Simple runner for przenies_niezrealizowane to avoid path/PowerShell quoting issues.

Usage:
  .venv/Scripts/python.exe trigger_przenies_runner.py 2026-03-29
"""
import sys
from tools import trigger_przenies

if __name__ == '__main__':
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    trigger_przenies.main(date_arg) if hasattr(trigger_przenies, 'main') else None
