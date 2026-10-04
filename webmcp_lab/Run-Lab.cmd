@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 serve.py --open
  goto done
)
where python >nul 2>nul
if not errorlevel 1 (
  python serve.py --open
  goto done
)
echo Python 3.10 or newer is required. Nothing has been installed or changed.
:done
pause
