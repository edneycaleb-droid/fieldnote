$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Get-Command py -ErrorAction SilentlyContinue)) { throw 'Python 3.11 or newer is required.' }
py -3 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\pip.exe install -e '.[browser,test]'
& .\.venv\Scripts\playwright.exe install chromium
$desktop = [Environment]::GetFolderPath('Desktop')
$shell = New-Object -ComObject WScript.Shell
foreach ($item in @(@('Record Workflow','record'),@('Replay Workflow','replay'))) {
  $shortcut = $shell.CreateShortcut((Join-Path $desktop ("$($item[0]).lnk")))
  $shortcut.TargetPath = 'powershell.exe'
  $shortcut.Arguments = "-NoExit -ExecutionPolicy Bypass -Command `"Set-Location '$PSScriptRoot'; Write-Host 'Use: .\.venv\Scripts\rrf.exe $($item[1])'`""
  $shortcut.WorkingDirectory = $PSScriptRoot
  $shortcut.Save()
}
& .\.venv\Scripts\pytest.exe -q
Write-Host 'Record & Replay Free installed and verified.' -ForegroundColor Green
