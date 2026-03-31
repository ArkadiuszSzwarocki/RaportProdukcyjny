<#
Create a Windows Scheduled Task that runs `run_backup.ps1` every hour.
Usage (run as administrator or a user with permission to create tasks):
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\create_hourly_backup_task.ps1 -TaskName "RP_Backup" -RunAsCurrentUser

Options:
  -TaskName string    Name of the scheduled task (default: RP_Backup)
  -RunAsCurrentUser   Create task to run as the current user (no password) and "Run only when user is logged on"
  -Force              Overwrite existing task with same name

Note: If you need the task to run when the user is not logged in, provide credentials or create the task with a service account.
#>

param(
    [string]$TaskName = 'RP_Backup',
    [switch]$RunAsCurrentUser = $true,
    [switch]$Force = $false,
    [int]$IntervalHours = 2
)

$projectRoot = Resolve-Path "$PSScriptRoot\.."
$projectPath = $projectRoot.Path.TrimEnd('\')
$runScript = Join-Path $projectPath 'scripts\run_backup.ps1'
if (-not (Test-Path $runScript)) {
    Write-Error "run_backup.ps1 not found at: $runScript"
    exit 2
}

# Build the action command to run PowerShell with the script
$action = "powershell -NoProfile -ExecutionPolicy Bypass -File `"$runScript`""

# If task exists and Force not specified, abort
$exists = schtasks /Query /TN "$TaskName" 2>$null
if ($LASTEXITCODE -eq 0) {
    if (-not $Force) {
        Write-Output "Task '$TaskName' already exists. Use -Force to replace."
        exit 0
    } else {
        Write-Output "Deleting existing task '$TaskName'..."
        schtasks /Delete /TN "$TaskName" /F | Out-Null
    }
}

# Create hourly schedule: every 1 hour
if ($RunAsCurrentUser) {
    # Create task that runs only when user is logged on (no password required)
    Write-Output "Creating scheduled task (every $IntervalHours hours) for current user..."
    & schtasks /Create /SC HOURLY /MO $IntervalHours /TN $TaskName /TR $action /F
} else {
    # Create task running as SYSTEM (requires admin) - use /RU SYSTEM
    Write-Output "Creating scheduled task (every $IntervalHours hours) as SYSTEM..."
    & schtasks /Create /SC HOURLY /MO $IntervalHours /TN $TaskName /TR $action /RU SYSTEM /F
}

if ($LASTEXITCODE -eq 0) {
    Write-Output "Scheduled task '$TaskName' created successfully."
} else {
    Write-Error "Failed to create scheduled task."
}
