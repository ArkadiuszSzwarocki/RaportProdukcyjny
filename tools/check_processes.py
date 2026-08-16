import subprocess
try:
    cmd = 'powershell -Command "Get-CimInstance Win32_Process -Filter \\"Name = \'python.exe\'\\" | Select-Object ProcessId, CommandLine | Format-Table -Wrap"'
    out = subprocess.check_output(cmd, shell=True)
    print(out.decode('utf-8', errors='ignore'))
except Exception as e:
    print("Error:", e)
