Hourly backup setup

Hourly backup setup

Files added:
- scripts/run_backup.ps1
- scripts/create_hourly_backup_task.ps1
- scripts/upload_backup.py

Quick usage:
1) Test backup manually:
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_backup.ps1

2) Create scheduled task running as SYSTEM (requires admin):
    Open elevated PowerShell (Run as Administrator) and run:
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\create_hourly_backup_task.ps1 -TaskName RP_Backup

    To create task for current user (no admin needed, runs only when user is logged on):
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\create_hourly_backup_task.ps1 -TaskName RP_Backup -RunAsCurrentUser

Rotation and retention
- The backup runner deletes files in `backups/` named `db-backup-*.sql` older than N days.
- Configure retention via environment variable `BACKUP_RETENTION_DAYS` (default: 7).

Upload to remote storage (optional)
- To upload backups automatically, set either S3 or FTP environment variables before the scheduled task runs.

S3 (recommended):
- Set environment variable `S3_BUCKET` to your bucket name.
- Optional: set `S3_KEY_PREFIX` to store backups under a prefix/path.
- AWS credentials can come from environment variables, AWS config, or instance role.

FTP (alternative):
- Set `FTP_HOST`, `FTP_USER`, `FTP_PASS` and optional `FTP_PATH`.

Examples (set system env vars when creating task or configure in Task Scheduler action):
- S3:
   setx S3_BUCKET "my-backups-bucket"
   setx S3_KEY_PREFIX "raporty"

- FTP:
   setx FTP_HOST "ftp.example.com"
   setx FTP_USER "ftpuser"
   setx FTP_PASS "secret"
   setx FTP_PATH "/backups"

Notes:
- Creating the scheduled task as SYSTEM requires Administrator privileges. Run create script in elevated PowerShell.
- Ensure Python packages: core scripts use only stdlib; S3 upload prefers boto3 (optional). If boto3 missing, script will try `aws cli`.
- Always verify backups and off-site copies.
