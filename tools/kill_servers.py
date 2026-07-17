import subprocess
try:
    cmd = 'powershell -Command "Get-CimInstance Win32_Process -Filter \\"Name = \'python.exe\'\\" | Where-Object { $_.CommandLine -like \'*app.py*\' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"'
    subprocess.check_call(cmd, shell=True)
    print("Successfully terminated all Python servers running app.py")
except Exception as e:
    print("Error:", e)
