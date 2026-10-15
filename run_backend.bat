@echo off
setlocal

cd /d "%~dp0"

set "PYTHON_EXE="

if exist ".venv\Scripts\python.exe" (
  set "PYTHON_EXE=.venv\Scripts\python.exe"
)

if exist ".venv\bin\python.exe" (
  set "PYTHON_EXE=.venv\bin\python.exe"
)

if "%PYTHON_EXE%"=="" (
  echo [INFO] Virtual environment not found. Creating .venv ...
  py -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Failed to create virtual environment.
    pause
    exit /b 1
  )
  if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
  )
)

if "%PYTHON_EXE%"=="" (
  echo [ERROR] Could not find Python inside .venv
  pause
  exit /b 1
)

if not exist "requirements.txt" (
  echo [ERROR] requirements.txt not found in %cd%
  pause
  exit /b 1
)

echo [INFO] Installing dependencies from requirements.txt...
"%PYTHON_EXE%" -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] Dependency installation failed.
  pause
  exit /b 1
)

echo [INFO] Starting Cloudburst backend...
echo [INFO] Working directory: %cd%
echo [INFO] Python: %PYTHON_EXE%
echo.

"%PYTHON_EXE%" "app.py"

set EXIT_CODE=%ERRORLEVEL%
echo.
echo [INFO] Backend stopped with exit code %EXIT_CODE%
pause
exit /b %EXIT_CODE%
