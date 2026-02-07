@echo off
setlocal
cd /d "%~dp0"
set "GH=gh"
if exist "C:\Program Files\GitHub CLI\gh.exe" set "GH=C:\Program Files\GitHub CLI\gh.exe"
if not exist "douyin_cookie.txt" (
  echo Cookie file not found: douyin_cookie.txt
  pause
  exit /b 1
)
"%GH%" auth status >nul 2>&1
if errorlevel 1 (
  echo Please login first: gh auth login
  pause
  exit /b 1
)
"%GH%" secret set DOUYIN_COOKIE -f "douyin_cookie.txt"
if errorlevel 1 (
  echo Failed to set secret.
  pause
  exit /b 1
)
echo Secret updated: DOUYIN_COOKIE
pause
