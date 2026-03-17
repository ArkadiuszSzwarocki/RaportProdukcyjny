# Run query_db_plan_produkcji.py with repo root on PYTHONPATH and venv activated
$Env:PYTHONPATH = (Get-Location).Path
& .\.venv\Scripts\Activate.ps1
python tools\query_db_plan_produkcji.py
