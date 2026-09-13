@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Cloudflare Autoreger

:: 1. Check local python in ./python/
if exist "%~dp0python\python.exe" (
    set "PYTHON_EXE=%~dp0python\python.exe"
    goto RUN
)

:: 2. Check Desktop\src\python
if exist "%USERPROFILE%\Desktop\src\python\python.exe" (
    echo [*] Kopirovanie Python iz Desktop\src...
    xcopy /E /I /Q /Y "%USERPROFILE%\Desktop\src\python" "%~dp0python" >nul 2>&1
    if exist "%~dp0python\python.exe" (
        set "PYTHON_EXE=%~dp0python\python.exe"
        goto RUN
    )
    set "PYTHON_EXE=%USERPROFILE%\Desktop\src\python\python.exe"
    goto RUN
)

if exist "C:\Users\Administrator\Desktop\src\python\python.exe" (
    echo [*] Kopirovanie Python iz Desktop\src...
    xcopy /E /I /Q /Y "C:\Users\Administrator\Desktop\src\python" "%~dp0python" >nul 2>&1
    if exist "%~dp0python\python.exe" (
        set "PYTHON_EXE=%~dp0python\python.exe"
        goto RUN
    )
    set "PYTHON_EXE=C:\Users\Administrator\Desktop\src\python\python.exe"
    goto RUN
)

:: 3. Check system python in PATH
where python >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_EXE=python"
    goto RUN
)

:: 4. Python not found anywhere - auto setup!
echo [*] Python ne nayden. Zapusk avtomaticheskoy nastroyki...
if exist "%~dp0setup.bat" (
    call "%~dp0setup.bat"
    if exist "%~dp0python\python.exe" (
        set "PYTHON_EXE=%~dp0python\python.exe"
        goto RUN
    )
)

echo ============================================================
echo  [!] OSHIBKA: Ne udalos ustanovit Python avtomaticheski!
echo ============================================================
echo.
pause
exit /b 1

:RUN
:: Auto-copy configs from Desktop\src if missing
if not exist "%~dp0emails.txt" (
    if exist "%USERPROFILE%\Desktop\src\emails.txt" copy "%USERPROFILE%\Desktop\src\emails.txt" "%~dp0emails.txt" >nul
    if exist "C:\Users\Administrator\Desktop\src\emails.txt" copy "C:\Users\Administrator\Desktop\src\emails.txt" "%~dp0emails.txt" >nul
)
if not exist "%~dp0proxies.txt" (
    if exist "%USERPROFILE%\Desktop\src\proxies.txt" copy "%USERPROFILE%\Desktop\src\proxies.txt" "%~dp0proxies.txt" >nul
    if exist "C:\Users\Administrator\Desktop\src\proxies.txt" copy "C:\Users\Administrator\Desktop\src\proxies.txt" "%~dp0proxies.txt" >nul
)

"%PYTHON_EXE%" "%~dp0launcher.py" %*
if errorlevel 1 (
    echo.
    pause
)
