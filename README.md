# lecture-notes

Автоматичний конвеєр для перетворення записів онлайн-лекцій, демо та презентацій у структуровані конспекти зі слайдами, транскриптом і OCR. Працює локально з GPU-прискоренням, на виході — готовий Google Doc, який можна завантажити в NotebookLM чи поділитись з колегами.

## Можливості

- 🎥 Детекція змін слайдів у записі екрана
- 🎙️ Транскрипція українською (або будь-якою іншою) через faster-whisper на GPU
- 🖼️ Витяг ключового кадру кожного слайда
- 🔗 Прив'язка розповіді до конкретного слайда за часом
- 🔤 OCR слайдів через Google Drive API (найкраща якість для української)
- 📄 Генерація готового Google Doc у папці `Lectures` з датою в назві
- 🧠 Окремий текстовий варіант, оптимізований для завантаження в NotebookLM

## Для кого

Протестовано на записах онлайн-зустрічей (Zoom, Meet, OBS) з трансляцією екрана — демо продуктів, воркшопи, презентації. Підтримує українську, англійську, російську, польську та інші мови (все, що підтримує whisper).

## Мови

За замовчуванням використовується автовизначення — whisper сам розпізнає мову з перших секунд. Якщо аудіо однорідне (одна мова весь час) — працює відмінно.

```bash
# Автовизначення (дефолт)
python process.py "lecture.mp4"

# Примусово конкретна мова
python process.py "lecture.mp4" --language uk  # українська
python process.py "lecture.mp4" --language en  # англійська
python process.py "lecture.mp4" --language ru  # російська
python process.py "lecture.mp4" --language pl  # польська
```

### Mixed-language контент (суржик, code-switching)

Whisper не має окремого режиму "суржик". Якщо твоє аудіо — українсько-російська суміш:
- `--language uk` змушує whisper транскрибувати все в українській орфографії (рекомендовано)
- `--language ru` — все в російській
- `--language auto` може переключатись між сегментами (часто плутається на суржику)

Для презентацій з термінологією іншою мовою (напр. українська розповідь + англійські терміни) — `--language uk` або `--language ru` зазвичай дає найкращий результат, бо whisper сам вставляє англіцизми.

## Privacy / Disclaimer

Цей інструмент використовує Google Drive API для OCR — слайди тимчасово завантажуються у твій Google Drive з параметром `ocrLanguage`, перетворюються в Google Doc (це тригерить Google OCR), текст читається, після чого тимчасовий документ автоматично видаляється. Оригінальне зображення слайда також потрапляє у твій Drive (у папку `Lectures` поруч з фінальним документом).

Якщо обробляєш конфіденційні матеріали — врахуй це і, можливо, використовуй `--google-doc` тільки для нечутливих записів, або перейди на локальний OCR (PaddleOCR/Tesseract) — це невеликий додатковий модуль, який можна додати.

## Приклад результату

Вхід: одне відео 1:36 годин демо CRM-системи.
Вихід:
- **39 слайдів** автоматично виявлено і збережено як PNG
- **1106 сегментів** розпізнаного тексту, прив'язаних до слайдів
- **Google Doc** з вбудованими картинками, OCR-текстом і транскрипцією
- Час обробки: ~12 хвилин на RTX 5060 Laptop

## Швидкий старт

### Вимоги

- Windows 10/11 (тестовано)
- Python 3.10-3.12
- NVIDIA GPU з 6+ ГБ VRAM (для large-v3) або 4+ ГБ (для medium). CPU теж працює, але повільніше.
- ffmpeg
- Google акаунт (для OCR через Drive API)

### Встановлення

```bash
# 1. Склонуй репозиторій
git clone https://github.com/skoropysAlex/lecture-notes.git
cd lecture-notes

# 2. Створи venv
python -m venv venv
# Windows
.\venv\Scripts\Activate.ps1
# Linux/Mac
# source venv/bin/activate

# 3. Встанови залежності
pip install -r requirements.txt

# 4. Встанови ffmpeg
# Windows: winget install ffmpeg
# Mac: brew install ffmpeg
# Linux: sudo apt install ffmpeg
```

### Налаштування Google Drive API (опціонально, для --google-doc)

1. Перейди в [Google Cloud Console](https://console.cloud.google.com/)
2. Створи новий проект
3. Увімкни Google Drive API і Google Docs API у бібліотеці
4. OAuth Consent Screen → External → додай себе в Test Users
5. Credentials → Create OAuth client ID → Desktop app
6. Завантаж JSON, перейменуй у `credentials.json`, поклади в корінь проекту

### Запуск

```bash
# Стадія 1 — транскрипція (довго)
python process.py "lecture.mp4" --model medium

# Стадія 2 — markdown + Google Doc з OCR (швидко, використовує кеш)
python process.py "lecture.mp4" --model medium --google-doc
```

Перший запуск з `--google-doc` відкриє браузер для авторизації.

### Windows: drag-and-drop

Перетягни відеофайл на `обробити_лекцію.bat` — виконає обидві стадії автоматично.

## Параметри

```
python process.py <video> [options]

--model MODEL                 faster-whisper model: tiny, base, small, medium, 
                              large-v3 (default: large-v3)
--language LANG               Код мови: auto, uk, en, ru, pl, та інші
                              (default: auto — whisper сам визначить)
--scene-threshold FLOAT       Чутливість детекції слайдів, менше = чутливіше
                              (default: 18, підібрано для screencast'ів)
--min-slide-duration FLOAT    Мінімальний інтервал між слайдами в секундах
                              (default: 5)
--google-doc                  Завантажити результат як Google Doc з OCR
--gdrive-parent-folder NAME   Назва папки в Drive (default: Lectures)
--output-dir DIR              Локальна папка для результатів (default: ./output)
```

## Чому дві стадії

На деяких конфігураціях (NVIDIA Blackwell + CUDA 13 + ctranslate2) Python-процес падає без traceback одразу після завершення транскрипції. Щоб не втрачати 15 хвилин GPU-роботи при кожному крашу, транскрипт кешується в JSON одразу після whisper. Другий запуск детектить кеш і оминає GPU-код взагалі, працює в чистому процесі.

Якщо на твоєму залізі крашу немає — можна об'єднати стадії одним викликом з `--google-doc`.

## Архітектура

```
video.mp4
    ├─→ PySceneDetect      → timestamps
    ├─→ ffmpeg             → slides/*.png
    ├─→ faster-whisper     → transcript.json (кеш)
    ├─→ merge by timestamp → notes.md + notes_for_notebooklm.md
    └─→ Google Drive API   → OCR + final Google Doc
```

## Стек

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — транскрипція
- [PySceneDetect](https://github.com/Breakthrough/PySceneDetect) — детекція змін кадру
- [ffmpeg](https://ffmpeg.org/) — витяг кадрів, обробка медіа
- [Google Drive/Docs API](https://developers.google.com/drive) — OCR та створення документів

## Ліцензія

MIT
