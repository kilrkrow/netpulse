@echo off
cd /d "%~dp0"
echo ============================================
echo  NetPulse - Building Windows Executable
echo ============================================
echo.

REM Install PyInstaller if not present
python -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    python -m pip install pyinstaller
)

echo.
echo Building NetPulse.exe ...
echo (This takes 1-3 minutes on first build)
echo.

REM Force pyqtgraph to use PySide6 (not PyQt6) during analysis
set QT_API=PySide6
set PYQTGRAPH_QT_LIB=PySide6

REM Run from spec file so workarounds (embed_manifest, icon) are preserved
python -m PyInstaller --noconfirm --clean NetPulse.spec

if errorlevel 1 (
    echo.
    echo BUILD FAILED. See output above.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  Build complete!
echo  Executable: dist\NetPulse\NetPulse.exe
echo ============================================
echo.
echo Notes:
echo   - dist\NetPulse\ is a self-contained folder (~120 MB)
echo   - Zip it and share - no Python install needed on target PC
echo   - First launch may be slow (AV scan); subsequent launches are fast
echo.
pause
