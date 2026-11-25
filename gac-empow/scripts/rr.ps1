param([Parameter(Mandatory=$true)][string]$Model, [Parameter(Mandatory=$true)][string]$Prefix,
      [string]$Mode = "normal", [Parameter(Mandatory=$true)][string]$Shots)
# render_set.ps1 with up to 3 retries until every requested shot PNG is newer than the start time.
$start = Get-Date
$list = $Shots.Split(",")
for ($i = 0; $i -lt 3; $i++) {
    $missing = @($list | Where-Object { $f = "$($Prefix)_$_.png"; -not ((Test-Path $f) -and ((Get-Item $f).LastWriteTime -gt $start)) })
    if ($missing.Count -eq 0) { break }
    & (Join-Path $PSScriptRoot "render_set.ps1") -Model $Model -Prefix $Prefix -Mode $Mode -Shots ($missing -join ",")
}
$missing = @($list | Where-Object { $f = "$($Prefix)_$_.png"; -not ((Test-Path $f) -and ((Get-Item $f).LastWriteTime -gt $start)) })
"missing: $($missing -join ',')"
