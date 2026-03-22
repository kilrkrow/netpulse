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

REM Use uv CPython (non-sandboxed) to seed the build venv
set UV_PYTHON=C:\Users\guysc\AppData\Roaming\uv\python\cpython-3.12.11-windows-x86_64-none\python.exe
set VENV=.venv-build
set PYTHON=%VENV%\Scripts\python.exe

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

REM Output outside Dropbox to avoid sync-lock failures on clean rebuild
set DISTPATH=C:\temp\NetPulse-dist
set WORKPATH=C:\temp\NetPulse-work

echo Build output: %DISTPATH% >> build.log

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
