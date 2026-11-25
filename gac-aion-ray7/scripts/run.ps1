param([Parameter(Mandatory=$true)][string]$Script, [string[]]$ScriptArgs = @(), [int]$Tail = 40)
# Runs a Blender Python script headless through the Microsoft Store launcher.
# Output goes to <script>[_args].log (written by wrap.py).
$launcher = "$env:LOCALAPPDATA\Microsoft\WindowsApps\BlenderFoundation.Blender_ppwjx1n5r4v9t\blender-launcher.exe"
$wrap = Join-Path $PSScriptRoot "wrap.py"
$Script = (Resolve-Path $Script).Path
$argList = @('--background','--factory-startup','--python',"`"$wrap`"",'--',"`"$Script`"") + $ScriptArgs
$p = Start-Process -FilePath $launcher -ArgumentList $argList -PassThru -Wait -WindowStyle Hidden
"exit: $($p.ExitCode)"
$words = @($ScriptArgs | Where-Object { $_ -match '^[A-Za-z_][A-Za-z0-9_]{0,11}$' })
$suffix = if ($words.Count) { "_" + ($words -join "_") } else { "" }
$log = [IO.Path]::ChangeExtension($Script, $null).TrimEnd('.') + $suffix + ".log"
if (Test-Path $log) { Get-Content $log -Tail $Tail } else { "no log written" }
