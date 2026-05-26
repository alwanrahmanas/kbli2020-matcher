$WshShell = New-Object -comObject WScript.Shell
$StartupDir = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"
$TargetFile = "$PSScriptRoot\run_backend.bat"
$ShortcutFile = "$StartupDir\KBLI_Backend.lnk"

if (-not (Test-Path $TargetFile)) {
    Write-Error "Could not find run_backend.bat at $TargetFile"
    exit 1
}

$Shortcut = $WshShell.CreateShortcut($ShortcutFile)
$Shortcut.TargetPath = $TargetFile
$Shortcut.WorkingDirectory = $PSScriptRoot
$Shortcut.Description = "Auto-start KBLI Backend"
$Shortcut.Save()

Write-Host "Success! Shortcut created at: $ShortcutFile"
Write-Host "The backend will now start automatically when you log in."
