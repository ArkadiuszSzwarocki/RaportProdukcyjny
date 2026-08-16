# Simple Makefile helpers for migrations
PY=python

migrate:
	@echo "Running migrations..."
	DB_USER=$(DB_USER) DB_PASS=$(DB_PASS) DB_NAME=$(DB_NAME) $(PY) run_migrations.py

rollback:
	@if [ -z "$(name)" ]; then echo "Provide name=<migration_basename> (e.g. 0001_add_wyjscie_columns)"; exit 1; fi
	@echo "Rolling back $(name)..."
	DB_USER=$(DB_USER) DB_PASS=$(DB_PASS) DB_NAME=$(DB_NAME) $(PY) run_migrations.py --down $(name)
