@echo off
cd /d "%~dp0"
echo ============================================
echo  NetPulse - Building Windows Executable
echo ============================================
echo.

REM Wipe any previous log so it never appends
if exist build.log del /f /q build.log

REM Timestamp the log
echo Build started: %DATE% %TIME% > build.log

REM ---------------------------------------------------------------------------
REM  Locate a non-sandboxed Python to seed the build venv.
REM
REM  Priority order:
REM    1. NETPULSE_PYTHON  – set this env var to override everything
REM    2. uv python find 3.12  – asks uv to locate its managed CPython 3.12
REM    3. python  – whatever is first on PATH (last resort)
REM ---------------------------------------------------------------------------
set VENV=.venv-build
set PYTHON=%VENV%\Scripts\python.exe

if defined NETPULSE_PYTHON (
    set UV_PYTHON=%NETPULSE_PYTHON%
    echo NETPULSE_PYTHON override: %UV_PYTHON% >> build.log
    goto :python_found
)

REM Try "uv python find 3.12" (requires uv on PATH)
for /f "usebackq delims=" %%P in (`uv python find 3.12 2^>nul`) do (
    set UV_PYTHON=%%P
)
if defined UV_PYTHON (
    echo uv python find: %UV_PYTHON% >> build.log
    goto :python_found
)

REM Final fallback – plain python on PATH
set UV_PYTHON=python
echo WARNING: uv not found; falling back to PATH python >> build.log

:python_found
echo Using base Python: %UV_PYTHON% >> build.log
"%UV_PYTHON%" --version >> build.log 2>&1

REM Create venv from uv CPython if it doesn't exist (or if base Python changed)
if not exist "%VENV%\Scripts\python.exe" (
    echo Creating build venv from uv CPython... >> build.log
    "%UV_PYTHON%" -m venv "%VENV%" >> build.log 2>&1
)

REM Install/upgrade build dependencies into the venv
echo Installing build dependencies... >> build.log
"%PYTHON%" -m pip install --upgrade --quiet pip >> build.log 2>&1
"%PYTHON%" -m pip install --quiet pyinstaller PySide6 pyqtgraph dnspython python-whois requests >> build.log 2>&1

echo.
echo Building NetPulse.exe ...
echo (This takes 1-3 minutes on first build)
echo (Output also logged to build.log)
echo.

REM Output outside Dropbox to avoid sync-lock failures on clean rebuild.
REM Uses %TEMP% (always set on Windows) unless overridden by env vars.
if not defined NETPULSE_DISTPATH set NETPULSE_DISTPATH=%TEMP%\NetPulse-dist
if not defined NETPULSE_WORKPATH set NETPULSE_WORKPATH=%TEMP%\NetPulse-work
set DISTPATH=%NETPULSE_DISTPATH%
set WORKPATH=%NETPULSE_WORKPATH%

echo Build output: %DISTPATH% >> build.log

REM Purge __pycache__ so PyInstaller never bundles stale .pyc bytecode
echo Clearing __pycache__ dirs... >> build.log
for /d /r . %%d in (__pycache__) do (
    if exist "%%d" rmdir /s /q "%%d" >> build.log 2>&1
)

REM Kill any running NetPulse instance so its DLLs aren't locked during clean
echo Stopping any running NetPulse.exe... >> build.log
taskkill /f /im NetPulse.exe > nul 2>&1
echo Taskkill exit: %errorlevel% >> build.log

REM Pre-delete dist ourselves so PyInstaller --clean never races with a lock
if exist "%DISTPATH%" (
    echo Pre-clearing dist folder... >> build.log
    rmdir /s /q "%DISTPATH%" >> build.log 2>&1
    REM Brief pause so the FS releases any residual handles
    timeout /t 2 /nobreak > nul
)

REM Force pyqtgraph to use PySide6 (not PyQt6) during analysis
set QT_API=PySide6
set PYQTGRAPH_QT_LIB=PySide6

REM Run from spec file using venv Python (uv CPython, no AppContainer sandbox)
"%PYTHON%" -m PyInstaller --noconfirm --clean --distpath "%DISTPATH%" --workpath "%WORKPATH%" NetPulse.spec >> build.log 2>&1

if errorlevel 1 (
    echo Build finished: %DATE% %TIME%  [FAILED] >> build.log
    echo.
    echo BUILD FAILED. See build.log for details.
    pause
    exit /b 1
)

echo Build finished: %DATE% %TIME%  [OK] >> build.log

echo.
echo ============================================
echo  Build complete!
echo  Executable: %DISTPATH%\NetPulse\NetPulse.exe
echo  Log saved:  build.log
echo ============================================
echo.
echo Notes:
echo   - %DISTPATH%\NetPulse\ is a self-contained folder (~120 MB)
echo   - Zip it and share - no Python install needed on target PC
echo   - First launch may be slow (AV scan); subsequent launches are fast
echo.
pause
