Migration files are stored here and applied in lexical order by `scripts/run_migrations.py`.

Conventions:
- Up migrations: `NNNN_description.sql` (applied automatically)
- Down migrations (rollback): `NNNN_description.down.sql`

Example:
- `0001_add_wyjscie_columns.sql` (adds columns)
- `0001_add_wyjscie_columns.down.sql` (drops columns)

How to run (example):

```bash
export DB_USER=myuser
export DB_PASS=mypass   # optional; if not set you'll be prompted
export DB_NAME=mydb
cd scripts
python run_migrations.py
```

Rollback example:

```bash
python run_migrations.py --down 0001_add_wyjscie_columns
```

Makefile helper:

```bash
cd scripts
make migrate DB_USER=myuser DB_PASS=mypass DB_NAME=mydb
make rollback name=0001_add_wyjscie_columns DB_USER=myuser DB_PASS=mypass DB_NAME=mydb
```
