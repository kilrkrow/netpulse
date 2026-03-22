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

REM Install PyInstaller if not present
python -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    python -m pip install pyinstaller >> build.log 2>&1
)

echo.
echo Building NetPulse.exe ...
echo (This takes 1-3 minutes on first build)
echo (Output also logged to build.log)
echo.

REM Force pyqtgraph to use PySide6 (not PyQt6) during analysis
set QT_API=PySide6
set PYQTGRAPH_QT_LIB=PySide6

REM Run from spec file so workarounds (embed_manifest, icon) are preserved
REM Tee output to console AND build.log (overwrite already handled above)
python -m PyInstaller --noconfirm --clean NetPulse.spec >> build.log 2>&1

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
echo  Executable: dist\NetPulse\NetPulse.exe
echo  Log saved:  build.log
echo ============================================
echo.
echo Notes:
echo   - dist\NetPulse\ is a self-contained folder (~120 MB)
echo   - Zip it and share - no Python install needed on target PC
echo   - First launch may be slow (AV scan); subsequent launches are fast
echo.
pause
