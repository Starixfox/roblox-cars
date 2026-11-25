param([string]$Variant = "High")
# Renders the full verification set of previews for one variant into roblox\previews.
$sc = $PSScriptRoot
$g = "C:\Users\jordan\RobloxCars\bmw-m4-gt3\roblox\BMW_M4GT3_$Variant.glb"
$p = "C:\Users\jordan\RobloxCars\bmw-m4-gt3\roblox\previews\" + $Variant.ToLower()
& "$sc\render_set.ps1" -Model $g -Prefix "${p}_normal" -Mode normal -Shots "front34,rear34,side,tyre,tyreR,wheel,interior,steer,frontbadge,rearbadge,top"
& "$sc\render_set.ps1" -Model $g -Prefix "${p}_dmg" -Mode dmg -Shots "windshield,rear34,sideglass"
& "$sc\render_set.ps1" -Model $g -Prefix "${p}_chunkcolors" -Mode chunkcolors -Shots "front34,rear34"
& "$sc\render_set.ps1" -Model $g -Prefix "${p}_groups" -Mode groupcolors -Shots "front34,rear34,top"
& "$sc\render_set.ps1" -Model $g -Prefix "${p}_impact" -Mode impact -Shots "front34,windshield"
& "$sc\render_set.ps1" -Model $g -Prefix "${p}_removeall" -Mode "remove:ALL" -Shots "front34,rear34,side,top"
& "$sc\render_set.ps1" -Model $g -Prefix "${p}_explode" -Mode explode -Shots "front34,rear34"
