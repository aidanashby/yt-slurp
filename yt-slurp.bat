@echo off
rem yt-slurp launcher: activates the virtual environment, asks for the main options, runs yt-slurp.
setlocal EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo No virtual environment at "%~dp0.venv".
    echo Set it up once with:
    echo     py -m venv .venv
    echo     .venv\Scripts\activate
    echo     pip install -e .
    pause
    exit /b 1
)
call ".venv\Scripts\activate.bat"

:menu
echo.
echo yt-slurp
echo   1  Fetch a channel or playlist
echo   2  Fetch every URL in a text file
echo   3  Merge Whisper transcripts into a folder
echo   4  Make the smoke-test WAVs
echo   Q  Quit
set "CHOICE="
set /p "CHOICE=Choose: "
if /i "!CHOICE!"=="1" goto fetch_url
if /i "!CHOICE!"=="2" goto fetch_file
if /i "!CHOICE!"=="3" goto merge
if /i "!CHOICE!"=="4" goto smoke
if /i "!CHOICE!"=="q" goto end
goto menu

:fetch_url
set "URL="
set /p "URL=Channel or playlist URL: "
if "!URL!"=="" goto menu
set "TARGET="!URL!""
goto options

:fetch_file
set "LIST="
set /p "LIST=Path to the text file of URLs (you can drag it here): "
set "LIST=!LIST:"=!"
if "!LIST!"=="" goto menu
set "TARGET=--file "!LIST!""
goto options

:options
set "OPTS="
set "TYPES="
set /p "TYPES=Types: videos, shorts, streams or all (Enter to be asked per channel): "
if not "!TYPES!"=="" set "OPTS=!OPTS! --types !TYPES!"
set "MINS="
set /p "MINS=Minimum minutes (Enter for 5): "
if not "!MINS!"=="" set "OPTS=!OPTS! --min-minutes !MINS!"
set "YN="
set /p "YN=Links only? (y/N): "
if /i "!YN!"=="y" set "OPTS=!OPTS! --links-only"
set "YN="
set /p "YN=Timestamps in transcripts? (y/N): "
if /i "!YN!"=="y" set "OPTS=!OPTS! --timestamps"
set "MORE="
set /p "MORE=Any other options (Enter for none, e.g. --limit 5): "
echo.
yt-slurp !TARGET! !OPTS! !MORE!
goto done

:merge
set "FOLDER="
set /p "FOLDER=Output folder for the channel or playlist (you can drag it here): "
set "FOLDER=!FOLDER:"=!"
if "!FOLDER!"=="" goto menu
set "OPTS="
set "YN="
set /p "YN=Delete each video's WAVs once merged? (y/N): "
if /i "!YN!"=="y" set "OPTS=--delete-wavs"
echo.
yt-slurp merge "!FOLDER!" !OPTS!
goto done

:smoke
echo.
yt-slurp smoke-wav
goto done

:done
echo.
pause
goto menu

:end
endlocal
