@echo off
setlocal

py -3.12 -m venv .venv
if errorlevel 1 py -3 -m venv .venv
if errorlevel 1 goto :error

.venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 goto :error
.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
if errorlevel 1 goto :error
npm install
if errorlevel 1 goto :error

echo.
echo Setup complete. Double-click start.bat or run it from Command Prompt.
exit /b 0

:error
echo.
echo Setup failed. Confirm Python 3.11/3.12 and Node.js 22 are installed.
exit /b 1

