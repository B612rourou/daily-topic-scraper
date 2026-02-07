@echo off
setlocal
set "REPO=%~dp0"
set "REPO=%REPO:~0,-1%"
set "GIT_EXE="
if exist "C:\Program Files\Git\cmd\git.exe" set "GIT_EXE=C:\Program Files\Git\cmd\git.exe"
if exist "C:\Program Files\Git\bin\git.exe" set "GIT_EXE=C:\Program Files\Git\bin\git.exe"
if "%GIT_EXE%"=="" set "GIT_EXE=git"

pushd "%REPO%" || (
  echo Failed to open repo: %REPO%
  pause
  exit /b 1
)

"%GIT_EXE%" rev-parse --abbrev-ref --symbolic-full-name @{u} >nul 2>&1
if errorlevel 1 (
  "%GIT_EXE%" branch --set-upstream-to=origin/main main >nul 2>&1
)

"%GIT_EXE%" pull
if errorlevel 1 (
  echo Pull failed.
  pause
  popd
  exit /b 1
)

echo Pull OK.
popd
pause
