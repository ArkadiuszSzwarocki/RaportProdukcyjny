param(
    [string]$LogPath = "logs\\app.log",
    [int]$Tail = 50
)

function Write-Info($m){ Write-Host "[tail_logs] $m" -ForegroundColor DarkGray }

if (-not (Test-Path $LogPath)) {
    Write-Host "Log file not found: $LogPath" -ForegroundColor Red
    exit 1
}

Write-Info "Tailing $LogPath (errors in RED, warnings in YELLOW)"

Get-Content -Path $LogPath -Tail $Tail -Wait | ForEach-Object {
    $line = $_
    try {
        if ($line -match '\b(ERROR|CRITICAL|Traceback)\b') {
            Write-Host $line -ForegroundColor Red
        } elseif ($line -match '\b(WARNING|Warn)\b') {
            Write-Host $line -ForegroundColor Yellow
        } else {
            Write-Host $line
        }
    } catch {
        Write-Host $line
    }
}
