param([Parameter(Mandatory=$true)][string]$Model, [Parameter(Mandatory=$true)][string]$Prefix,
      [string]$Mode = "normal", [Parameter(Mandatory=$true)][string]$Shots)
# render_set.ps1 with up to 3 retries until every requested shot PNG is newer than the start time.
# Safety (low-memory PC): only start Blender when no blender process exists and >= 600 MB RAM is free.
function Wait-Safe {
    for ($i = 0; $i -lt 40; $i++) {               # up to ~20 min for other Blender jobs to finish
        if (-not (Get-Process blender* -ErrorAction SilentlyContinue)) { break }
        Start-Sleep 30
    }
    if (Get-Process blender* -ErrorAction SilentlyContinue) { return "blender still running" }
    for ($i = 0; $i -lt 5; $i++) {
        $free = [int]((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1024)
        if ($free -ge 600) { return $null }
        Start-Sleep 30
    }
    return "low RAM ($free MB free)"
}
$start = Get-Date
$list = $Shots.Split(",")
for ($i = 0; $i -lt 3; $i++) {
    $missing = @($list | Where-Object { $f = "$($Prefix)_$_.png"; -not ((Test-Path $f) -and ((Get-Item $f).LastWriteTime -gt $start)) })
    if ($missing.Count -eq 0) { break }
    $why = Wait-Safe
    if ($why) { "ABORT: $why"; break }
    & (Join-Path $PSScriptRoot "render_set.ps1") -Model $Model -Prefix $Prefix -Mode $Mode -Shots ($missing -join ",")
}
$missing = @($list | Where-Object { $f = "$($Prefix)_$_.png"; -not ((Test-Path $f) -and ((Get-Item $f).LastWriteTime -gt $start)) })
"missing: $($missing -join ',')"
