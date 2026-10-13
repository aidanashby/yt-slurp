@echo off
rem ==========================================================================
rem  yt-slurp: installer and launcher. Double-click this file.
rem
rem  Checks what this computer already has, installs or repairs only what is
rem  missing (asking first), then opens the yt-slurp window. When everything
rem  is already set up it just opens the window.
rem
rem  Keep this file plain ASCII with Windows (CRLF) line endings.
rem ==========================================================================
setlocal EnableExtensions EnableDelayedExpansion
title yt-slurp
cd /d "%~dp0"
set "HERE=%~dp0"
set "VENV=%HERE%.venv"
set "VPY=%VENV%\Scripts\python.exe"
set "VPYW=%VENV%\Scripts\pythonw.exe"
set "WINGET_LINKS=%LOCALAPPDATA%\Microsoft\WinGet\Links"
set "WINGET_PKGS=%LOCALAPPDATA%\Microsoft\WinGet\Packages"
set "WINGET_OPTS=-e --accept-package-agreements --accept-source-agreements --disable-interactivity"

echo.
echo  yt-slurp
echo  --------
echo.

rem ----- 1. Is the window already open? -------------------------------------
set "LOCKFILE=%APPDATA%\yt-slurp\gui.lock"
if exist "%LOCKFILE%" (
    set /p OTHERPID=<"%LOCKFILE%"
    tasklist /FI "PID eq !OTHERPID!" 2>nul | findstr /i "python" >nul
    if not errorlevel 1 (
        echo  yt-slurp is already open. Bringing it to the front.
        echo %RANDOM%>"%APPDATA%\yt-slurp\raise.request"
        timeout /t 2 >nul
        exit /b 0
    )
)

rem ----- 2. Updates from GitHub (asks first) --------------------------------
if "%~1"=="updated" goto after_update
where git >nul 2>nul || goto after_update
if not exist "%HERE%.git" goto after_update
for /f "delims=" %%b in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set "BRANCH=%%b"
if /i not "%BRANCH%"=="main" goto after_update
echo  Checking for a newer version...
git fetch --quiet origin main >nul 2>nul || goto after_update
for /f "delims=" %%h in ('git rev-parse HEAD') do set "LOCALREV=%%h"
for /f "delims=" %%h in ('git rev-parse origin/main') do set "REMOTEREV=%%h"
if "%LOCALREV%"=="%REMOTEREV%" goto after_update
git merge-base --is-ancestor HEAD origin/main >nul 2>nul || goto after_update
set "DIRTY="
for /f "delims=" %%s in ('git status --porcelain --untracked-files=no') do set "DIRTY=1"
if defined DIRTY (
    echo  A newer version is available, but files here have been edited, so it was not updated.
    goto after_update
)
choice /c YN /n /m "  A newer version of yt-slurp is available. Update now? [Y/N] "
if errorlevel 2 goto after_update
rem The update can change this file while it runs, so pull and restart in one
rem parsed block: cmd reads a block whole before running any of it.
(
    git pull --ff-only --quiet origin main
    "%COMSPEC%" /c ""%~f0" updated"
    exit /b
)
:after_update

rem ----- 3. Python -----------------------------------------------------------
rem Reuse the virtual environment if it works and has Tkinter.
if exist "%VPY%" (
    "%VPY%" -c "import sys, tkinter; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
    if not errorlevel 1 (
        echo  Python: using the existing environment.
        goto python_ready
    )
    echo  The existing environment is broken. Rebuilding it.
    rmdir /s /q "%VENV%"
)

call :find_python
if not defined PY (
    echo.
    echo  No Python 3.10 or later with Tkinter was found.
    choice /c YN /n /m "  Install Python 3.12 for your user account with winget? [Y/N] "
    if errorlevel 2 goto fail_python
    winget install Python.Python.3.12 --scope user %WINGET_OPTS%
    call :find_python
    if not defined PY goto fail_python
)
echo  Python: %PY%
echo  Creating the environment in .venv ...
"%PY%" -m venv "%VENV%"
if errorlevel 1 goto fail_venv
if exist "%VENV%\installed-pyproject.toml" del "%VENV%\installed-pyproject.toml"
:python_ready

rem ----- 4. ffmpeg and ffprobe -----------------------------------------------
call :find_ffmpeg
if not defined FFDIR (
    echo.
    echo  ffmpeg was not found. yt-slurp needs it to make WAV files.
    choice /c YN /n /m "  Install ffmpeg with winget? [Y/N] "
    if errorlevel 2 goto fail_ffmpeg
    winget install Gyan.FFmpeg %WINGET_OPTS%
    call :find_ffmpeg
    if not defined FFDIR goto fail_ffmpeg
)
if not "%FFDIR%"=="ON_PATH" set "PATH=%FFDIR%;%PATH%"
echo  ffmpeg: found.

rem ----- 5. Deno (yt-dlp needs it to read YouTube) ---------------------------
call :find_deno
if not defined DENO (
    echo.
    echo  Deno was not found. yt-dlp needs it to read YouTube.
    choice /c YN /n /m "  Install Deno with winget? [Y/N] "
    if errorlevel 2 goto fail_deno
    winget install DenoLand.Deno %WINGET_OPTS%
    call :find_deno
    if not defined DENO goto fail_deno
)
set "YT_SLURP_DENO=%DENO%"
for %%d in ("%DENO%") do set "PATH=%%~dpd;%PATH%"
echo  Deno: found.

rem ----- 6. Libraries ---------------------------------------------------------
rem Install when pyproject.toml has changed since the last install, or when
rem the libraries cannot be imported.
set "NEEDINSTALL="
if not exist "%VENV%\installed-pyproject.toml" set "NEEDINSTALL=1"
if not defined NEEDINSTALL (
    fc /b "%HERE%pyproject.toml" "%VENV%\installed-pyproject.toml" >nul 2>nul || set "NEEDINSTALL=1"
)
if not defined NEEDINSTALL (
    "%VPY%" -c "import yt_dlp, yt_slurp, yt_slurp_gui, pytest" >nul 2>nul || set "NEEDINSTALL=1"
)
if defined NEEDINSTALL (
    echo  Installing yt-slurp and its libraries. This takes a minute the first time...
    "%VPY%" -m pip install --quiet --disable-pip-version-check --upgrade pip
    "%VPY%" -m pip install --quiet --disable-pip-version-check -e "%HERE%.[dev]"
    if errorlevel 1 goto fail_pip
    copy /y "%HERE%pyproject.toml" "%VENV%\installed-pyproject.toml" >nul
    type nul > "%VENV%\ytdlp-updated.stamp"
)

rem YouTube changes often break old yt-dlp versions, so update it weekly.
"%VPY%" -c "import os, sys, time; p = r'%VENV%\ytdlp-updated.stamp'; sys.exit(0 if os.path.exists(p) and time.time() - os.path.getmtime(p) < 7 * 86400 else 1)" >nul 2>nul
if errorlevel 1 (
    echo  Checking for a newer yt-dlp ^(weekly^)...
    "%VPY%" -m pip install --quiet --disable-pip-version-check --upgrade "yt-dlp[default]"
    if errorlevel 1 (
        echo  Could not update yt-dlp. Carrying on with the current version.
    ) else (
        type nul > "%VENV%\ytdlp-updated.stamp"
    )
)

rem ----- 7. Open the window ---------------------------------------------------
echo.
echo  Opening the yt-slurp window...
start "" "%VPYW%" -m yt_slurp gui
timeout /t 2 >nul
exit /b 0


rem ==========================================================================
rem  Helpers
rem ==========================================================================

:find_python
rem Prefer the newest of 3.13 to 3.10 (tested), then newer versions.
set "PY="
set "CHECK=import sys, tkinter; assert sys.version_info >= (3, 10); print(sys.executable)"
where py >nul 2>nul
if not errorlevel 1 (
    for %%v in (3.13 3.12 3.11 3.10 3.14 3.15 3) do (
        if not defined PY (
            for /f "delims=" %%p in ('py -%%v -c "%CHECK%" 2^>nul') do set "PY=%%p"
        )
    )
)
if defined PY exit /b 0
for /f "delims=" %%p in ('python -c "%CHECK%" 2^>nul') do set "PY=%%p"
if defined PY exit /b 0
for %%d in ("%LOCALAPPDATA%\Programs\Python\Python3*" "%ProgramFiles%\Python3*" "%LOCALAPPDATA%\Python\pythoncore-3*") do (
    for /d %%e in (%%d) do (
        if not defined PY if exist "%%e\python.exe" (
            for /f "delims=" %%p in ('call "%%e\python.exe" -c "%CHECK%" 2^>nul') do set "PY=%%p"
        )
    )
)
exit /b 0

:find_ffmpeg
set "FFDIR="
where ffmpeg >nul 2>nul && where ffprobe >nul 2>nul && (set "FFDIR=ON_PATH" & exit /b 0)
if exist "%WINGET_LINKS%\ffmpeg.exe" if exist "%WINGET_LINKS%\ffprobe.exe" (set "FFDIR=%WINGET_LINKS%" & exit /b 0)
for /d %%p in ("%WINGET_PKGS%\Gyan.FFmpeg*") do (
    for /d %%q in ("%%p\ffmpeg-*") do (
        if exist "%%q\bin\ffmpeg.exe" set "FFDIR=%%q\bin"
    )
)
if defined FFDIR exit /b 0
for %%d in ("C:\ffmpeg\bin" "%ProgramFiles%\ffmpeg\bin" "%USERPROFILE%\ffmpeg\bin") do (
    if not defined FFDIR if exist "%%~d\ffmpeg.exe" if exist "%%~d\ffprobe.exe" set "FFDIR=%%~d"
)
exit /b 0

:find_deno
set "DENO="
for /f "delims=" %%p in ('where deno 2^>nul') do if not defined DENO set "DENO=%%p"
if defined DENO exit /b 0
for %%c in ("%USERPROFILE%\.deno\bin\deno.exe" "%WINGET_LINKS%\deno.exe") do (
    if not defined DENO if exist "%%~c" set "DENO=%%~c"
)
if defined DENO exit /b 0
for /d %%p in ("%WINGET_PKGS%\DenoLand.Deno*") do (
    if exist "%%p\deno.exe" set "DENO=%%p\deno.exe"
)
exit /b 0


rem ==========================================================================
rem  Failures: say what went wrong and how to fix it, then wait.
rem ==========================================================================

:fail_python
echo.
echo  yt-slurp needs Python 3.10 or later, including Tkinter.
echo  Install it from https://www.python.org/downloads/ and tick "tcl/tk and IDLE"
echo  during installation, then double-click yt-slurp.bat again.
goto fail_end

:fail_venv
echo.
echo  Could not create the environment with %PY%.
echo  Delete the .venv folder here if it exists, then double-click yt-slurp.bat again.
goto fail_end

:fail_ffmpeg
echo.
echo  yt-slurp needs ffmpeg. Install it with winget, or download it from
echo  https://www.gyan.dev/ffmpeg/builds/ and unzip it to C:\ffmpeg,
echo  then double-click yt-slurp.bat again.
goto fail_end

:fail_deno
echo.
echo  yt-slurp needs Deno. Install it from https://deno.com, then double-click
echo  yt-slurp.bat again.
goto fail_end

:fail_pip
echo.
echo  Installing the libraries failed. Check the internet connection and
echo  double-click yt-slurp.bat again. If it fails again, copy the messages
echo  above and send them to Claude.
goto fail_end

:fail_end
echo.
pause
exit /b 1
