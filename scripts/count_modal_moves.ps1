$matches = Select-String -Path logs\app.log -Pattern 'Modal-move debug' | ForEach-Object {
    $m = $_.Line -replace '.*Modal-move debug: ',''
    try { $o = ConvertFrom-Json $m } catch { continue }
    if ($o.moved) { $o.id }
}

$matches | Group-Object | Sort-Object Count -Descending | Format-Table Count, Name -AutoSize
Write-Host "TOTAL:" ($matches | Measure-Object).Count
