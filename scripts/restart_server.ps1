<#
.SYNOPSIS
    Bezpieczny restart aplikacji Flask (app.py) nasłuchującej na porcie 8082.

.DESCRIPTION
    Skrypt zatrzymuje proces nasłuchujący na zadanym porcie (domyślnie 8082),
    uruchamia `python app.py` i weryfikuje, czy serwer zaczął nasłuchiwać.

.EXAMPLE
    .\restart_server.ps1
    .\restart_server.ps1 -Port 8082 -Retries 5
#>

param(
    [int]$Port = 8082,
    [string]$PythonExe = "python",
    [string]$AppFile = "app.py",
    [int]$Retries = 3,
    [int]$WaitSec = 10
)

function Write-Info($msg) {
    Write-Output "[restart_server] $msg"
}

Write-Info "Restarting server for port $Port (app=$AppFile)..."

for ($attempt = 1; $attempt -le $Retries; $attempt++) {
    Write-Info "Attempt $attempt of $Retries"

    $conn = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conn) {
        $procId = $conn.OwningProcess
        try {
            Write-Info "Found process ${procId} listening on port $Port. Stopping..."
            Stop-Process -Id $procId -Force -ErrorAction Stop
            Start-Sleep -Seconds $WaitSec
        } catch {
            $err = $_
            Write-Info "Failed to stop process ${procId}: ${err}"
        }
    } else {
        Write-Info "No existing process on port $Port."
    }

    Write-Info "Starting $PythonExe $AppFile..."
    $proc = Start-Process -FilePath $PythonExe -ArgumentList $AppFile -WorkingDirectory (Get-Location).Path -PassThru

    Start-Sleep -Seconds ($WaitSec + 1)

    $newConn = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($newConn) {
        Write-Info "Server started OK (pid=$($newConn.OwningProcess))."
        exit 0
    } else {
        Write-Info "Server not listening yet. Stopping started process (pid=$($proc.Id)) and retrying..."
        try { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue } catch {}
        Start-Sleep -Seconds $WaitSec
    }
}

Write-Info "Nie udało się uruchomić serwera po $Retries próbach."
exit 1
