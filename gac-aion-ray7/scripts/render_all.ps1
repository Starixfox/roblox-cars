param([string]$Variant = "High", [string]$Only = "")
# Renders the full verification set of one variant. Retries a mode when Blender crashed before writing.
$s = $PSScriptRoot
$root = Split-Path $s -Parent
$m = Join-Path $root "roblox\GAC_AionRay7_$Variant.glb"
$p = Join-Path $root ("roblox\previews\" + $Variant.ToLower())
$off = "remove:Hood+Trunk+Door_L+Door_R+Door_RL+Door_RR+FrontBumper+RearBumper+Mirror_L+Mirror_R+Wheel_LF+Wheel_RF+Wheel_LR+Wheel_RR"
$jobs = @(
    @("normal", "", "front34,rear34,side,tyre,wheel,rearbadge,frontbadge,dash,interior"),
    @($off, "_off", "front34,rear34,side,top"),
    @("dmg", "_dmg", "windshield,sideglass,rear34"),
    @("chunkcolors", "_chunks", "front34,rear34,top"),
    @("impact", "_impact", "front34,windshield"),
    @("explode", "_explode", "front34,rear34")
)
foreach ($j in $jobs) {
    if ($Only -and $j[1] -ne $Only) { continue }
    $start = Get-Date
    for ($try = 1; $try -le 3; $try++) {
        & "$s\render_set.ps1" -Model $m -Prefix ($p + $j[1]) -Mode $j[0] -Shots $j[2]
        $first = $j[2].Split(",")[-1]
        $f = "$p$($j[1])_$first.png"
        if ((Test-Path $f) -and ((Get-Item $f).LastWriteTime -gt $start)) { break }
        "retry $($j[0]) ($try)"
    }
}
"ALL RENDERS DONE"
