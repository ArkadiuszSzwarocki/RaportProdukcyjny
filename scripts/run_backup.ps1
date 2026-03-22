<#
Run database backup using project's virtualenv python and `scripts/backup_database.py`.
Usage: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_backup.ps1
#>

Param(
    [string]$ProjectRoot = "",
    [string]$OutDir = ""
)

if ($ProjectRoot) {
    try {
        $project = Resolve-Path $ProjectRoot
    } catch {
        $project = Resolve-Path "$PSScriptRoot\.."
    }
} else {
    $project = Resolve-Path "$PSScriptRoot\.."
}

if (-not $OutDir) {
    $OutDir = Join-Path $PSScriptRoot '..\backups'
}

$projectPath = $project.Path.TrimEnd('\')
$venvPython = Join-Path $projectPath ".venv\Scripts\python.exe"
$python = if (Test-Path $venvPython) { $venvPython } else { 'python' }

# Ensure backups dir exists
if (-not (Test-Path $OutDir)) {
    New-Item -ItemType Directory -Path $OutDir | Out-Null
}

$timestamp = (Get-Date).ToString('yyyyMMdd-HHmmss')
$outFile = Join-Path $OutDir ("db-backup-$timestamp.sql")

Write-Output "Running backup: $outFile"

$scriptPath = Join-Path $projectPath 'scripts\backup_database.py'
if (-not (Test-Path $scriptPath)) {
    Write-Error "Cannot find backup script: $scriptPath"
    exit 2
}

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $python
$psi.Arguments = "`"$scriptPath`" --out `"$outFile`""
$psi.UseShellExecute = $false
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$proc = [System.Diagnostics.Process]::Start($psi)
$stdout = $proc.StandardOutput.ReadToEnd()
$stderr = $proc.StandardError.ReadToEnd()
$proc.WaitForExit()

Write-Output $stdout
if ($stderr) { Write-Error $stderr }

if ($proc.ExitCode -ne 0) {
    Write-Error "Backup script exited with code $($proc.ExitCode)"
    exit $proc.ExitCode
}

Write-Output "Backup finished: $outFile"

# ROTACJA: usuń pliki starsze niż N dni (domyślnie 1 = 24 godziny)
# Możesz nadpisać ustawieniem env: BACKUP_RETENTION_DAYS (liczba dni)
$retention = [int]($env:BACKUP_RETENTION_DAYS -as [int])
if (-not $retention -or $retention -le 0) { $retention = 1 }
Write-Output "Rotacja: usuwanie backupow starszych niz $retention dni z $OutDir"
Get-ChildItem -Path $OutDir -Filter 'db-backup-*.sql' -File | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$retention) } | ForEach-Object {
    Write-Output "Usuwam: $($_.FullName) (ostatnia modyfikacja: $($_.LastWriteTime))"
    try { Remove-Item -Path $_.FullName -Force -ErrorAction Stop } catch { Write-Warning "Nie udalo sie usunac $_.FullName: $_" }
}

# Upload backup if configured (S3 or FTP) via Python helper
$uploader = Join-Path $projectPath 'scripts\upload_backup.py'
if (Test-Path $uploader) {
    Write-Output "Wywoluje upload: $uploader"
    $upPsi = New-Object System.Diagnostics.ProcessStartInfo
    $upPsi.FileName = $python
    $upPsi.Arguments = "`"$uploader`" `"$outFile`""
    $upPsi.UseShellExecute = $false
    $upPsi.RedirectStandardOutput = $true
    $upPsi.RedirectStandardError = $true
    $upproc = [System.Diagnostics.Process]::Start($upPsi)
    $upOut = $upproc.StandardOutput.ReadToEnd()
    $upErr = $upproc.StandardError.ReadToEnd()
    $upproc.WaitForExit()
    Write-Output $upOut
    if ($upErr) { Write-Error $upErr }
    if ($upproc.ExitCode -ne 0) { Write-Warning "Upload zakonczony z kodem $($upproc.ExitCode)" }
} else {
    Write-Output "Brak helpera upload_backup.py; pomijam upload." 
}

exit 0
