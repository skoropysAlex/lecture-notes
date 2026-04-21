@echo off
chcp 65001 >nul
setlocal

REM ===================================================================
REM  Lecture processor — one-click launcher
REM
REM  Use one of:
REM    1. Drag-and-drop a video file onto this .bat
REM    2. Double-click and paste video path when asked
REM
REM  Does both stages automatically:
REM    - Transcription (GPU, with cached resume if it crashes)
REM    - Markdown + Google Doc with OCR
REM ===================================================================

cd /d "%~dp0"

REM If video was drag-dropped onto the .bat
if not "%~1"=="" (
    set "VIDEO=%~1"
    goto :run
)

REM Otherwise — ask for path
echo.
echo ==========================================================
echo   Process lecture ^(transcript + Google Doc^)
echo ==========================================================
echo.
set /p "VIDEO=Drag a video file here ^(or type its path^) and press Enter: "

REM Strip quotes if user dragged a file into the prompt
set VIDEO=%VIDEO:"=%

:run
if not exist "%VIDEO%" (
    echo.
    echo [ERROR] File not found: %VIDEO%
    pause
    exit /b 1
)

echo.
echo Processing: %VIDEO%
echo.

REM Activate venv
call "%~dp0venv\Scripts\activate.bat"
if errorlevel 1 (
    echo [ERROR] Failed to activate venv.
    echo Check that the venv folder exists in %~dp0
    pause
    exit /b 1
)

REM ---- Stage 1: transcription ----
REM Uses medium model by default — change to large-v3 for better quality (slower)
REM --no-confirm-language: skip interactive language prompt so drag-and-drop
REM doesn't hang waiting for input. Whisper auto-detects from first 30s.
echo ==========================================================
echo   Stage 1/2: Transcription ^(GPU, ~10-15 min per hour of video^)
echo ==========================================================
echo.

python process.py "%VIDEO%" --model medium --no-confirm-language

REM ctranslate2 may crash Python after transcription on some Blackwell GPUs —
REM that's OK, the transcript was cached. We just continue to stage 2.

echo.
echo ==========================================================
echo   Stage 2/2: Markdown + Google Doc with OCR
echo ==========================================================
echo.

python process.py "%VIDEO%" --model medium --google-doc --no-confirm-language
if errorlevel 1 (
    echo.
    echo [ERROR] Stage 2 failed.
    pause
    exit /b 1
)

echo.
echo ==========================================================
echo   Done! Results:
echo     - Local files in the output\ folder
echo     - Google Doc link shown in the logs above
echo ==========================================================
echo.
pause
