param([Parameter(Mandatory=$true)][string]$Model, [Parameter(Mandatory=$true)][string]$Prefix,
      [string]$Mode = "normal", [string]$Shots = "")
# Renders preview shots of a .glb. Blender may crash on exit after rendering; the images are still written.
$launcher = "$env:LOCALAPPDATA\Microsoft\WindowsApps\BlenderFoundation.Blender_ppwjx1n5r4v9t\blender-launcher.exe"
$s = $PSScriptRoot
$a = @('--background','--factory-startup','--python',"`"$s\wrap.py`"",'--',"`"$s\render.py`"","`"$Model`"","`"$Prefix`"",$Mode)
if ($Shots) { $a += $Shots }
$p = Start-Process -FilePath $launcher -ArgumentList $a -PassThru -Wait -WindowStyle Hidden
"render $Mode exit $($p.ExitCode)"
