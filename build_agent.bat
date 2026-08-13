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

REM ── Copy artifacts to media\assets\agent for download ──────────
echo [INFO] Copying build artifacts to media\assets\agent for download...
if not exist "media\assets\agent" mkdir "media\assets\agent"
if exist "media\assets\agent\agent.exe" del /q "media\assets\agent\agent.exe"
copy /Y "dist\agent.exe" "media\assets\agent\agent.exe"
echo [OK] Artifacts available for download at /media/assets/agent/

echo.
echo ========================================
echo  Build complete!
echo ========================================
echo.
echo  Agent:  dist\agent.exe  (standalone single file)
echo  Download URL (served by backend):
echo    /media/assets/agent/agent.exe
echo.
pause
endlocal