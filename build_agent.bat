@echo off
REM ============================================================
REM  Build agent.exe with PyInstaller (production-ready)
REM
REM  Usage:  build_agent.bat
REM
REM  Output: dist\agent\agent.exe
REM ============================================================

setlocal
cd /d "%~dp0"

echo.
echo ========================================
echo  Building AutoSocial AI Agent EXE
echo ========================================
echo.

REM Activate venv
call .venv\Scripts\activate.bat

REM Clean previous builds
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM Build with PyInstaller
python -m PyInstaller agent_build.spec --clean --noconfirm

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed!
    exit /b 1
)

echo.
echo ========================================
echo  Build complete!
echo ========================================
echo.
echo  Agent:  dist\agent.exe  (standalone single file)
echo.
pause
endlocal