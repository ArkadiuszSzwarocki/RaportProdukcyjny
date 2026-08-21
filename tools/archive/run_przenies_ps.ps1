# Activate venv and run the przenies script with repo PYTHONPATH
$Env:PYTHONPATH = (Get-Location).Path
& .\.venv\Scripts\Activate.ps1
python tools\run_przenies.py
