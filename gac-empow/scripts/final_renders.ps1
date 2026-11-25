# Re-renders every listed preview, one Blender process at a time (rr.ps1 checks processes and RAM).
$s = $PSScriptRoot
$root = Split-Path $s -Parent
$p = Join-Path $root "roblox\previews"
$rm = "remove:Hood+Trunk+Door_L+Door_R+Door_RL+Door_RR+FrontBumper+RearBumper+Mirror_L+Mirror_R+Wheel_LF+Wheel_RF+Wheel_LR+Wheel_RR"
& "$s\rr.ps1" -Model "$s\work\orig_norm.glb" -Prefix "$p\orig" -Mode normal -Shots "front34,rear34,wheel"
foreach ($v in "High", "Lite") {
    $m = Join-Path $root "roblox\GAC_Empow_$v.glb"
    $k = $v.ToLower()
    & "$s\rr.ps1" -Model $m -Prefix "$p\$k" -Mode normal -Shots "front34,rear34,wheel,tyre,caliper,frontbadge,rearbadge,steer"
    & "$s\rr.ps1" -Model $m -Prefix "$p\$($k)_rm" -Mode $rm -Shots "front34,rear34,side"
    & "$s\rr.ps1" -Model $m -Prefix "$p\$($k)_dmg" -Mode dmg -Shots "windshield"
    & "$s\rr.ps1" -Model $m -Prefix "$p\$($k)_impact" -Mode impact -Shots "front34,windshield"
    & "$s\rr.ps1" -Model $m -Prefix "$p\$($k)_cc" -Mode chunkcolors -Shots "front34,rear34"
    & "$s\rr.ps1" -Model $m -Prefix "$p\$($k)_explode" -Mode explode -Shots "front34"
}
"ALL RENDERS FINISHED"
