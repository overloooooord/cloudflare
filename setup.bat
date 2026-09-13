@echo off
cd /d "%~dp0"
title "Cloudflare Autoreger - Setup & Build"
color 0A

echo ============================================================
echo    CLOUDFLARE AUTOREGER - SETUP ^& BUILD (UNIFIED)
echo ============================================================
echo.

set "PY_DIR=%~dp0python"
set "PYTHON_EXE=%PY_DIR%\python.exe"
set "VENDOR_DIR=%~dp0vendor"

rem --------------------------------------------------------------
rem 1. Check/Install Portable Python and dependencies
rem --------------------------------------------------------------
if exist "%PYTHON_EXE%" (
    echo [OK] Portable Python found.
    goto CHECK_VENDOR
)

echo [!] Portable Python not found in \python\ folder.
echo     Starting automated download and package build...
echo.

echo [1/3] Downloading Portable Python 3.11.9...
powershell -Command "& { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip' -OutFile '%TEMP%\python_embed.zip' }"
if not exist "%TEMP%\python_embed.zip" (
    echo [X] Failed to download Portable Python!
    pause
    exit /b 1
)

echo    [...] Extracting...
if not exist "%PY_DIR%" mkdir "%PY_DIR%"
powershell -Command "Expand-Archive -Path '%TEMP%\python_embed.zip' -DestinationPath '%PY_DIR%' -Force"
del "%TEMP%\python_embed.zip" >nul 2>&1

echo    [...] Enabling site-packages...
powershell -Command "(Get-Content '%PY_DIR%\python311._pth') -replace '#import site', 'import site' | Set-Content '%PY_DIR%\python311._pth'"

echo    [...] Installing pip...
powershell -Command "& { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%PY_DIR%\get-pip.py' }"
"%PYTHON_EXE%" "%PY_DIR%\get-pip.py"
del "%PY_DIR%\get-pip.py" >nul 2>&1
echo    [OK] Portable Python ready!

:CHECK_VENDOR
if exist "%VENDOR_DIR%" (
    echo [OK] Vendor packages directory found.
    goto CHECK_VCREDIST
)

echo.
echo [2/3] Downloading all pip packages into vendor/ folder...
mkdir "%VENDOR_DIR%"
"%PYTHON_EXE%" -m pip download -r "%~dp0requirements.txt" -d "%VENDOR_DIR%"
if %errorlevel% neq 0 (
    echo    [X] Failed to download packages!
    pause
    exit /b 1
)
echo    [OK] All packages downloaded to vendor/

:CHECK_VCREDIST
rem --------------------------------------------------------------
rem 2. Install Visual C++ Redistributable
rem --------------------------------------------------------------
echo.
echo Checking Visual C++ Redistributable...
reg query "HKLM\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\X64" >nul 2>&1
if %errorlevel% equ 0 goto VCREDIST_INSTALLED

if not exist "%~dp0vc_redist.x64.exe" goto VCREDIST_MISSING
echo    [...] Installing Visual C++ Redistributable...
"%~dp0vc_redist.x64.exe" /install /quiet /norestart
echo    [OK] Visual C++ Redistributable installed
goto VCREDIST_DONE

:VCREDIST_MISSING
echo    [!] vc_redist.x64.exe not found in package!
echo        Please download and install it manually if needed.
goto VCREDIST_DONE

:VCREDIST_INSTALLED
echo    [OK] Visual C++ Redistributable is already installed

:VCREDIST_DONE

rem --------------------------------------------------------------
rem 3. Install/Update pip packages offline
rem --------------------------------------------------------------
echo.
echo Installing/Verifying Python packages...
"%PYTHON_EXE%" -m pip install --find-links "%VENDOR_DIR%" -r "%~dp0requirements.txt"
if %errorlevel% neq 0 (
    echo    [!] Offline installation failed/incomplete. Trying online installation...
    "%PYTHON_EXE%" -m pip install -r "%~dp0requirements.txt"
)
if %errorlevel% neq 0 (
    echo    [X] Error installing packages!
    pause
    exit /b 1
)
echo    [OK] All packages verified and installed.

rem --------------------------------------------------------------
rem 4. Verify Requests Engine
rem --------------------------------------------------------------
echo.
echo Verifying engine...
"%PYTHON_EXE%" -c "import curl_cffi, aiohttp, rich; print('[OK] Pure requests engine ready.')" 2>nul
if %errorlevel% neq 0 (
    echo    [...] Installing engine dependencies...
    "%PYTHON_EXE%" -m pip install curl-cffi aiohttp aiofiles certifi rich
)
echo    [OK] Engine ready.

rem --------------------------------------------------------------
rem DONE
rem --------------------------------------------------------------
echo.
echo ============================================================
echo    [OK] SETUP COMPLETED! Everything is ready.
echo ============================================================
echo.
echo    Now:
echo    1. Edit config.py (Captcha API key, proxies, etc.)
echo    2. Put proxies in proxies.txt
echo    3. Run: start.bat
echo.
pause
