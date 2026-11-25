param([Parameter(Mandatory=$true)][string]$Variant, [Parameter(Mandatory=$true)][string]$Mode,
      [Parameter(Mandatory=$true)][string]$Shots, [string]$Name = "")
# Low-memory safe render: waits until no Blender process runs and enough RAM is free, then renders (one process at a time).
$sc = $PSScriptRoot
for ($i = 0; $i -lt 40; $i++) {
    $busy = @(Get-Process blender -ErrorAction SilentlyContinue).Count
    $free = [int]((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1024)
    if ($busy -eq 0 -and $free -ge 600) { break }
    "waiting: blender=$busy free=${free}MB"
    Start-Sleep -Seconds 30
}
if ($busy -ne 0 -or $free -lt 600) { "ABORT: blender=$busy free=${free}MB"; exit 1 }
if (-not $Name) { $Name = ($Mode -replace '[^A-Za-z]', '') }
$g = "C:\Users\jordan\RobloxCars\bmw-m4-gt3\roblox\BMW_M4GT3_$Variant.glb"
$p = "C:\Users\jordan\RobloxCars\bmw-m4-gt3\roblox\previews\" + $Variant.ToLower() + "_" + $Name
"free ${free}MB, rendering $Mode"
& "$sc\render_set.ps1" -Model $g -Prefix $p -Mode $Mode -Shots $Shots
