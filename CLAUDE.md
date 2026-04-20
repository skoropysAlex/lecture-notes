# Lecture Notes Pipeline

Автоматичний конвеєр для перетворення записів онлайн-лекцій / демо / презентацій у структуровані конспекти з синхронізованими слайдами, транскриптом і OCR.

## Що робить

На вхід: відеофайл (mp4 тощо) з лекції — типово screencast з трансляцією екрана, вебкамерою в кутку, розповіддю українською.

На виході:
1. **`notes.md`** — локальний markdown з вбудованими слайдами і транскриптом, прив'язаним за часом (для Claude Code, для людського перегляду)
2. **`notes_for_notebooklm.md`** — той самий контент без картинок, проза замість таймкодів (оптимізовано для індексації в NotebookLM)
3. **`<video>.transcript.json`** — кеш транскрипту, дозволяє resume при крашах
4. **Google Doc у папці "Lectures"** — єдиний документ зі слайдами + OCR-текстом з кожного слайда + транскриптом. Готовий до завантаження в NotebookLM як source.

## Як користуватись

Основний шлях (для не-технічного користувача):
```
Перетягни відео на обробити_лекцію.bat
```

Технічний шлях:
```bash
# Стадія 1: транскрипція (GPU, ~10-15 хв на годину відео)
python process.py "лекція.mp4" --model medium

# Стадія 2: markdown + Google Doc з OCR (~2-3 хв)
python process.py "лекція.mp4" --model medium --google-doc
```

Дві стадії потрібні через відомий краш ctranslate2 на деяких GPU (див. нижче).

## Архітектура

```
video.mp4
    │
    ├─ [1/4] PySceneDetect (ContentDetector, threshold=18)
    │        ↓ timestamps of slide changes
    │
    ├─ [2/4] ffmpeg extracts one frame per slide (1s offset past transition)
    │        ↓ slides/slide_NNN.png
    │
    ├─ [3/4] faster-whisper (large-v3 або medium, GPU через CUDA)
    │        ↓ transcript segments with timestamps
    │        ↓ cached to <video>.transcript.json
    │
    ├─ [4/4] merge: для кожного слайда — його сегменти whisper за часом
    │        ↓ notes.md + notes_for_notebooklm.md
    │
    └─ [5/5] (optional) Google Drive export:
             - OCR each slide via Drive's convert-to-Google-Doc trick
             - Build single Google Doc: [slide image + OCR text + transcript] × N
             - All under a persistent "Lectures" folder
```

## Tuning

- **`--scene-threshold`** (default 18) — знизити якщо пропускає слайди, підняти якщо ловить зміни як слайди. 18 підібрано під screencast'и з overlay вебкамерою в кутку (рухливий елемент змушує PySceneDetect вимагати сильних змін, тому стандартні 27 пропускають частину реальних переходів).
- **`--model`** — `medium` швидший (~8-12x realtime на RTX 5060) і достатньо точний для української. `large-v3` точніший на термінології/іменах, але повільніший (~5-7x realtime).
- **`--min-slide-duration`** (default 5с) — мінімальний інтервал між слайдами. Підвищити якщо демо-секції генерують багато псевдо-слайдів на клацання.
- **`--language`** (default `auto`) — whisper auto-detect з перших секунд. Явно вказувати (uk/en/ru/pl) коли:
  - Аудіо з суржиком чи code-switching (auto може стрибати між мовами посегментно)
  - Перші секунди немає мовлення (auto ловить шум і не визначає)
  - Потрібна жорстка гарантія однорідного виводу в одній орфографії
  - Для OCR слайдів використовується та сама визначена мова (береться з кешу після транскрипції)

## Відомі проблеми / обходи

### Blackwell (RTX 50xx) + CUDA 13 + ctranslate2 = hard crash after transcription
На деяких конфігураціях Python-процес падає без Exception одразу після `model.transcribe()`, коли ctranslate2 вивільняє CUDA-ресурси. Проявляється як тиша в терміналі — скрипт повертає control у PowerShell без traceback.

**Обхід:** пайплайн розбитий на дві стадії. Транскрипт кешується у JSON **до** потенційного крашу. Другий запуск зчитує кеш і минає GPU-код взагалі. Див. `обробити_лекцію.bat`.

### CUDA DLLs not found
`ctranslate2` шукає `cublas64_12.dll` через C++ `LoadLibrary`, яке **ігнорує** `os.add_dll_directory()`. Має працювати через `os.environ["PATH"]`. Скрипт це робить автоматично на старті (`[init] Registered N CUDA DLL paths from venv`).

### Google Drive OAuth
Перший запуск з `--google-doc` відкриває браузер для авторизації. Токен зберігається в `token.json` поруч з `credentials.json`. Наступні запуски проходять без UI.

### OCR через Google Drive (а не локальний)
Ми використовуємо Drive API з параметром `ocrLanguage=uk` — це перетворює завантажену картинку в Google Doc з розпізнаним текстом, потім ми його забираємо як plain text і видаляємо проміжний документ. Якість української тут значно краща, ніж у локальних OCR-движків (Tesseract/EasyOCR/PaddleOCR).

## Стек

- **Транскрипція:** faster-whisper 1.2+ (ctranslate2 backend)
- **Детекція слайдів:** scenedetect 0.6 (ContentDetector)
- **Кадри:** ffmpeg (CLI)
- **OCR:** Google Drive API (не локальний движок)
- **Google Doc:** google-api-python-client + OAuth installed app flow
- **GPU:** CUDA 12/13, cuDNN 9 (з pip-пакетів nvidia-*)

## Файли

- `process.py` — головний пайплайн
- `google_drive_export.py` — модуль для Drive/Docs API (auth, OCR, doc build)
- `обробити_лекцію.bat` — wrapper для drag-drop на Windows
- `credentials.json` — OAuth client (з Google Cloud Console, не коммітити)
- `token.json` — OAuth token після першого запуску (не коммітити)
- `*.transcript.json` — кеш транскриптів (не коммітити)
- `output/<video_name>/` — локальні результати

## Залежності

```
# Core
pip install faster-whisper scenedetect[opencv]

# CUDA runtime (обов'язково на Windows для GPU)
pip install nvidia-cudnn-cu12

# Google Drive integration
pip install google-auth google-auth-oauthlib google-api-python-client
```

Плюс `ffmpeg` у системному PATH.

## Workflow для нових лекцій

1. Записав лекцію (Zoom, Meet, OBS — що завгодно)
2. Поклав mp4 у будь-яку папку
3. Перетягнув на `обробити_лекцію.bat`
4. ~15 хв зачекав
5. Отримав Google Doc у Drive/Lectures, готовий для NotebookLM

## Плани / не зроблено

- [ ] Об'єднати дві стадії в один запуск через subprocess-ізоляцію transcribe() (обхід Blackwell крашу)
- [ ] Додати detection screencast vs presentation → різні дефолтні threshold
- [ ] Batch-processing: перетягнути папку з N відео → обробити по черзі
- [ ] Конвертація notes.md у PDF через pandoc
- [ ] Опціональне об'єднання кадрів з рядом (A/B) якщо зміна була плавна (анімація появи буллетів)
