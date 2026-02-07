@echo off
setlocal
cd /d "%~dp0"
set "PY=python"
if exist "C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe" set "PY=C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe"
set "HEADLESS=0"
"%PY%" scraper.py
pause
