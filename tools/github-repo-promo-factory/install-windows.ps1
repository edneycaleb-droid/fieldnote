$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw 'Install Node.js 22 LTS, then run this again.' }
npm install
npm run doctor
$desktop = [Environment]::GetFolderPath('Desktop')
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut((Join-Path $desktop 'GitHub Promo Factory.lnk'))
$shortcut.TargetPath = 'powershell.exe'
$shortcut.Arguments = "-NoExit -ExecutionPolicy Bypass -Command `"Set-Location '$PSScriptRoot'; npm run studio`""
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.Save()
Write-Host 'Installed. Desktop shortcut created.' -ForegroundColor Green
