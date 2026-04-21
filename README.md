# lecture-notes

> 🇺🇸 English (you are here) · 🇺🇦 [Українська версія](README.uk.md)

**GPU-accelerated pipeline for converting lecture, webinar, and screencast recordings into searchable Google Docs.** Detects slide transitions automatically, transcribes audio in 100+ languages via [faster-whisper](https://github.com/SYSTRAN/faster-whisper), runs OCR on every slide, and assembles the result into a single well-structured Google Doc ready for NotebookLM, review, or sharing.

Built for Zoom, Google Meet, Microsoft Teams, and OBS recordings — anything where someone presents slides while talking.

## Why

Traditional solutions for turning a recorded lecture into notes are all bad in some way:

- **Manual transcription** — hours of work per hour of video
- **YouTube auto-captions** — no slides, poor formatting, limited languages
- **Otter.ai / Fireflies** — no slide images, subscription, privacy concerns for internal content
- **Whisper alone** — transcript only, no visual context

This tool fills the gap: **one command, one Google Doc, slides + synchronized transcript + OCR on every slide**, all running locally on your GPU. Free forever. Works with any language Whisper supports.

## Features

- 🎥 **Automatic slide detection** — scene-change algorithm tuned for screencasts with overlay webcam windows
- 🎙️ **Multilingual transcription** — 100+ languages via faster-whisper, GPU-accelerated, auto-detection
- 🖼️ **Key frame extraction** — one high-quality PNG per slide, offset past transitions
- 🔗 **Time-synchronized narrative** — every transcript segment is attached to the slide that was on screen when it was spoken
- 🔤 **Slide OCR** — Google Drive API OCR handles any text baked into slide images (diagrams, screenshots, non-editable PDFs). Excellent for Cyrillic, Latin, Arabic scripts alike.
- 📄 **Google Doc output** — embeds slides inline, dated filename, organized in a `Lectures` folder
- 🧠 **NotebookLM-friendly version** — separate plain-text file optimized for feeding into [NotebookLM](https://notebooklm.google.com/)

## Who it's for

Tested extensively on recordings of:
- Online meetings (Zoom, Google Meet, Microsoft Teams) with screen sharing
- Product demos, internal workshops, training sessions
- Conference talks, university lectures
- OBS/local screen captures

Supports any language Whisper supports (100+, including English, Spanish, Portuguese, French, German, Chinese, Japanese, Arabic, Russian, Ukrainian, Polish, and many more).

## Example output

Input: one 1h 36m CRM demo recording (~40 slides, overlay webcam, CRM software UI in slides).

Output:
- **39 slides** detected automatically, saved as PNG
- **1,106 transcript segments** attached to the correct slide
- **Single Google Doc** with inline slide images, OCR'd slide text, and full transcript
- Processing time: **~12 minutes** on RTX 5060 Laptop (8 GB VRAM), `medium` Whisper model

## Quick start

### Requirements

- Windows 10/11, Linux, or macOS (Windows tested most extensively)
- Python 3.10–3.12
- NVIDIA GPU with 6+ GB VRAM for `large-v3`, or 4+ GB for `medium`. CPU works too (slower).
- ffmpeg
- Google account (only if you want the `--google-doc` output; the Markdown pipeline works offline)

### Installation

```bash
# 1. Clone
git clone https://github.com/skoropysAlex/lecture-notes.git
cd lecture-notes

# 2. Create virtualenv
python -m venv venv
# Windows:
.\venv\Scripts\Activate.ps1
# Linux/Mac:
# source venv/bin/activate

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Install ffmpeg
# Windows: winget install ffmpeg
# Mac:     brew install ffmpeg
# Linux:   sudo apt install ffmpeg
```

### Google Drive API setup (optional, for `--google-doc`)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable **Google Drive API** and **Google Docs API** in the library
4. OAuth Consent Screen → External → add your own email to Test Users
5. Credentials → Create OAuth client ID → **Desktop app**
6. Download the JSON, rename to `credentials.json`, place in project root

### Run

```bash
# Stage 1 — transcription (slow: ~10–15 min per hour of video on mid-range GPU)
python process.py "lecture.mp4" --model medium

# Stage 2 — Markdown + Google Doc with OCR (fast, uses cached transcript)
python process.py "lecture.mp4" --model medium --google-doc
```

First `--google-doc` run opens a browser for OAuth authorization.

### Windows: drag-and-drop

Drop your video file onto `process_lecture.bat` — both stages run automatically.

## Parameters

```
python process.py <video> [options]

--model MODEL                 faster-whisper model: tiny, base, small, medium,
                              large-v3 (default: large-v3)
--language LANG               Language code: auto, en, es, pt, fr, de, uk, ru,
                              pl, zh, ja, ar, and any other Whisper-supported
                              code (default: auto — Whisper detects)
--no-confirm-language         Skip interactive language confirmation. Useful
                              for batch/scripted runs (used by the .bat file).
--scene-threshold FLOAT       Slide-change sensitivity, lower = more sensitive
                              (default: 18, tuned for screencasts with overlay
                              webcams)
--min-slide-duration FLOAT    Minimum seconds between slide changes
                              (default: 5)
--google-doc                  Upload result as Google Doc with OCR
--gdrive-parent-folder NAME   Drive folder name (default: Lectures)
--output-dir DIR              Local output folder (default: ./output)
```

## Mixed-language content

For content with multiple languages (technical terms in English inside a non-English presentation, code-switching, etc.):
- Force the dominant language with `--language <code>` — Whisper will keep foreign terms as-is in that language's orthography
- `--language auto` may switch between segments (sometimes wrongly)

## Privacy & disclaimer

This tool uses Google Drive API. A few important data-handling notes:

**OCR (short-lived):** slide images are temporarily uploaded to your Drive with `ocrLanguage` set, converted to Google Docs (which triggers Google's OCR), the text is read, and the temporary doc is deleted. Only the image files remain.

**Slide images (persistent):** the original PNG files of slides stay in your Drive inside the `Lectures` folder next to the final Google Doc. They remain there until you delete them.

**⚠️ Brief public exposure during embedding:** Google Docs API requires images to be publicly accessible when inserting them into a document (the API fetches the URL server-side). The script grants `anyone with link` read access *temporarily* and revokes it immediately after insertion. For most use cases this is fine, but if you're processing **highly sensitive content** (medical, financial, NDA material), be aware of this short window (seconds to minutes depending on slide count).

**For confidential content:** run the pipeline **without** `--google-doc` — nothing leaves your machine, you still get local `notes.md` with slides and transcript. Or swap Google Drive OCR for a local alternative (PaddleOCR / Tesseract) — a small additional module.

## Why two stages?

On some hardware configurations (NVIDIA Blackwell RTX 50-series + CUDA 13 + ctranslate2), the Python process crashes silently without a traceback immediately after Whisper finishes transcribing. To avoid losing 15 minutes of GPU work on every crash, the transcript is cached to JSON immediately after the transcription completes. The second run detects the cache, skips the GPU code entirely, and runs in a clean process.

If your hardware doesn't trigger this crash, you can merge both stages into a single call with `--google-doc`.

## Architecture

```
video.mp4
    ├─→ PySceneDetect      → timestamps
    ├─→ ffmpeg             → slides/*.png
    ├─→ faster-whisper     → transcript.json (cached)
    ├─→ merge by timestamp → notes.md + notes_for_notebooklm.md
    └─→ Google Drive API   → OCR + final Google Doc
```

## Stack

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — transcription (ctranslate2-based, GPU accelerated)
- [PySceneDetect](https://github.com/Breakthrough/PySceneDetect) — scene-change detection
- [ffmpeg](https://ffmpeg.org/) — frame extraction, media processing
- [Google Drive/Docs API](https://developers.google.com/drive) — OCR and document generation

## Contributing

Issues and pull requests welcome. Particularly interested in:
- Alternative local OCR backends (PaddleOCR, Tesseract) for fully offline workflows
- Testing on macOS and Linux with Apple Silicon / AMD GPUs
- Better slide deduplication for presentations with animated transitions
- Support for other note-taking destinations (Notion, Obsidian, Logseq)

## License

[MIT](LICENSE)
