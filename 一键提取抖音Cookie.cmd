@echo off
setlocal
cd /d "%~dp0"

:: admin check
>nul 2>&1 "%SYSTEMROOT%\system32\cacls.exe" "%SYSTEMROOT%\system32\config\system"
if errorlevel 1 (
  echo Requesting Administrator permission...
  powershell -Command "Start-Process '%~f0' -Verb RunAs"
  exit /b
)

set "PY=python"
if exist "C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe" set "PY=C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe"

"%PY%" -m pip install -r requirements.txt
"%PY%" "extract_cookie.py"
if errorlevel 1 (
  echo.
  echo  extraction failed. You can try: ???????Cookie.cmd
)
pause
