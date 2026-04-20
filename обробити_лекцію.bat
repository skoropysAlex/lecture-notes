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
echo   Обробка лекції ^(транскрипт + Google Doc^)
echo ==========================================================
echo.
set /p "VIDEO=Перетягни відеофайл сюди ^(або введи шлях^) і натисни Enter: "

REM Strip quotes if user dragged a file into the prompt
set VIDEO=%VIDEO:"=%

:run
if not exist "%VIDEO%" (
    echo.
    echo [ERROR] Файл не знайдено: %VIDEO%
    pause
    exit /b 1
)

echo.
echo Обробляю: %VIDEO%
echo.

REM Activate venv
call "%~dp0venv\Scripts\activate.bat"
if errorlevel 1 (
    echo [ERROR] Не вдалось активувати venv.
    echo Перевір чи папка venv існує в %~dp0
    pause
    exit /b 1
)

REM ---- Stage 1: transcription ----
REM Uses medium model by default — change to large-v3 for better quality (slower)
REM --no-confirm-language: skip interactive language prompt so drag-and-drop
REM doesn't hang waiting for input. Whisper auto-detects from first 30s.
echo ==========================================================
echo   Етап 1/2: Транскрипція ^(GPU, ~10-15 хв на годину відео^)
echo ==========================================================
echo.

python process.py "%VIDEO%" --model medium --no-confirm-language

REM ctranslate2 may crash Python after transcription on some Blackwell GPUs —
REM that's OK, the transcript was cached. We just continue to stage 2.

echo.
echo ==========================================================
echo   Етап 2/2: Markdown + Google Doc з OCR
echo ==========================================================
echo.

python process.py "%VIDEO%" --model medium --google-doc --no-confirm-language
if errorlevel 1 (
    echo.
    echo [ERROR] Етап 2 завершився з помилкою.
    pause
    exit /b 1
)

echo.
echo ==========================================================
echo   ✓ Готово! Результати:
echo     - Локальні файли у папці output\
echo     - Google Doc — посилання вище в логах
echo ==========================================================
echo.
pause
