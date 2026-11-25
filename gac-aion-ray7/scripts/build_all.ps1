param([string[]]$Variants = @("high", "lite"), [switch]$Render)
# Builds the variants one after another (never two Blenders at once), optionally renders each set.
$s = $PSScriptRoot
function Wait-Safe {
    for ($k = 0; $k -lt 40; $k++) {
        $busy = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Name -like 'blender*' }).Count
        $free = [int]((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1024)
        if ($busy -eq 0 -and $free -ge 600) { return $true }
        "waiting: blender processes $busy, free RAM $free MB"
        Start-Sleep 30
    }
    return $false
}
foreach ($v in $Variants) {
    if (-not (Wait-Safe)) { "STOPPED before $v build: not safe to start Blender"; exit 1 }
    & "$s\run.ps1" -Script "$s\prep.py" -ScriptArgs $v -Tail 1
    Select-String -Path "$s\prep_$v.log" -Pattern 'visible tris|Traceback|FAILED' | ForEach-Object { $_.Line }
}
if ($Render) {
    foreach ($v in $Variants) { & "$s\render_all.ps1" -Variant ((Get-Culture).TextInfo.ToTitleCase($v)) }
}
"BUILD_ALL DONE"
