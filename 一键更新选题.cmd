@echo off
setlocal
set "REPO=%~dp0"
set "REPO=%REPO:~0,-1%"
set "GIT_EXE="
if exist "C:\Program Files\Git\cmd\git.exe" set "GIT_EXE=C:\Program Files\Git\cmd\git.exe"
if exist "C:\Program Files\Git\bin\git.exe" set "GIT_EXE=C:\Program Files\Git\bin\git.exe"
if "%GIT_EXE%"=="" set "GIT_EXE=git"
set "PY=python"
if exist "C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe" set "PY=C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe"

pushd "%REPO%" || (
  echo Failed to open repo: %REPO%
  pause
  exit /b 1
)

"%GIT_EXE%" rev-parse --is-inside-work-tree >nul 2>&1 || (
  echo Not a git repo: %REPO%
  pause
  popd
  exit /b 1
)

"schtasks" /Query /TN "DouyinDailyTopics" >nul 2>&1
if errorlevel 1 (
  echo Creating daily task (08:00)...
  schtasks /Create /TN "DouyinDailyTopics" /TR "%REPO%\一键更新选题.cmd" /SC DAILY /ST 08:00 /F >nul 2>&1
  if errorlevel 1 (
    echo Failed to create scheduled task. Please run this file as Administrator once.
  ) else (
    echo Scheduled task created.
  )
)

"%GIT_EXE%" rev-parse --abbrev-ref --symbolic-full-name @{u} >nul 2>&1
if errorlevel 1 (
  "%GIT_EXE%" branch --set-upstream-to=origin/main main >nul 2>&1
)

echo Syncing...
"%GIT_EXE%" pull --rebase

echo Running scraper...
"%PY%" scraper.py
if errorlevel 1 (
  echo Scraper failed.
  pause
  popd
  exit /b 1
)

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set "TODAY=%%i"

"%GIT_EXE%" add "每日选题/*.md"
for /f %%i in ('"%GIT_EXE%" status --porcelain') do set HAS_CHANGES=1
if not defined HAS_CHANGES (
  echo No changes to commit.
  popd
  pause
  exit /b 0
)

"%GIT_EXE%" commit -m "chore: 添加每日选题 %TODAY%"
"%GIT_EXE%" push
if errorlevel 1 (
  echo Push failed.
  pause
  popd
  exit /b 1
)

echo Done.
popd
pause
