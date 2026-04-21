# Lecture Notes Pipeline

Automated pipeline that turns recordings of online lectures / demos / presentations into structured notes with synchronized slides, transcript, and OCR.

## What it does

Input: a video file (mp4 or similar) of a lecture — typically a screencast with screen sharing, a webcam overlay in the corner, and a spoken narration in any language.

Output:
1. **`notes.md`** — local markdown with embedded slides and a time-synchronized transcript (for Claude Code, for human review)
2. **`notes_for_notebooklm.md`** — the same content without images, prose instead of timestamps (optimized for indexing in NotebookLM)
3. **`<video>.transcript.json`** — transcript cache, allows resuming after crashes
4. **Google Doc in the `Lectures` folder** — single document with slides + OCR text from each slide + transcript. Ready to upload into NotebookLM as a source.

## Usage

Primary path (for a non-technical user):
```
Drag the video file onto process_lecture.bat
```

Technical path:
```bash
# Stage 1: transcription (GPU, ~10-15 min per hour of video)
python process.py "lecture.mp4" --model medium

# Stage 2: markdown + Google Doc with OCR (~2-3 min)
python process.py "lecture.mp4" --model medium --google-doc
```

Two stages are needed because of a known ctranslate2 crash on some GPUs (see below).

## Architecture

```
video.mp4
    │
    ├─ [1/4] PySceneDetect (ContentDetector, threshold=18)
    │        ↓ timestamps of slide changes
    │
    ├─ [2/4] ffmpeg extracts one frame per slide (1s offset past transition)
    │        ↓ slides/slide_NNN.png
    │
    ├─ [3/4] faster-whisper (large-v3 or medium, GPU via CUDA)
    │        ↓ transcript segments with timestamps
    │        ↓ cached to <video>.transcript.json
    │
    ├─ [4/4] merge: for each slide — its whisper segments by time
    │        ↓ notes.md + notes_for_notebooklm.md
    │
    └─ [5/5] (optional) Google Drive export:
             - OCR each slide via Drive's convert-to-Google-Doc trick
             - Build single Google Doc: [slide image + OCR text + transcript] × N
             - All under a persistent "Lectures" folder
```

## Tuning

- **`--scene-threshold`** (default 18) — lower it if slides are being missed, raise it if it's catching non-slide changes. 18 is tuned for screencasts with an overlay webcam in the corner (the moving element forces PySceneDetect to require stronger changes, so the default 27 misses some real transitions).
- **`--model`** — `medium` is faster (~8-12x realtime on RTX 5060) and accurate enough for most languages. `large-v3` is more accurate on terminology and proper names, but slower (~5-7x realtime).
- **`--min-slide-duration`** (default 5s) — minimum interval between slides. Raise it if demo sections generate many pseudo-slides from clicks.
- **`--language`** (default `auto`) — whisper auto-detects from the first few seconds. Set it explicitly (en/es/fr/de/uk/…) when:
  - Audio has code-switching (auto may jump between languages segment by segment)
  - No speech in the first few seconds (auto catches noise and fails to detect)
  - You need a hard guarantee of uniform output in one orthography
  - The same detected language is used for slide OCR (taken from the cache after transcription)

## Known issues / workarounds

### Blackwell (RTX 50xx) + CUDA 13 + ctranslate2 = hard crash after transcription
On some configurations, the Python process dies without an Exception right after `model.transcribe()`, when ctranslate2 releases CUDA resources. It shows up as silence in the terminal — the script returns control to PowerShell without a traceback.

**Workaround:** the pipeline is split into two stages. The transcript is cached to JSON **before** the potential crash. The second run reads the cache and bypasses the GPU code entirely. See `process_lecture.bat`.

### CUDA DLLs not found
`ctranslate2` looks for `cublas64_12.dll` via C++ `LoadLibrary`, which **ignores** `os.add_dll_directory()`. It needs to work through `os.environ["PATH"]`. The script does this automatically at startup (`[init] Registered N CUDA DLL paths from venv`).

### Google Drive OAuth
First run with `--google-doc` opens a browser for authorization. The token is saved in `token.json` next to `credentials.json`. Subsequent runs pass without UI.

### OCR via Google Drive (not local)
We use the Drive API with `ocrLanguage=<lang>` — this converts an uploaded image into a Google Doc with recognized text, then we read it as plain text and delete the intermediate doc. Quality is significantly better than local OCR engines (Tesseract/EasyOCR/PaddleOCR), especially for non-Latin scripts.

## Stack

- **Transcription:** faster-whisper 1.2+ (ctranslate2 backend)
- **Slide detection:** scenedetect 0.6 (ContentDetector)
- **Frames:** ffmpeg (CLI)
- **OCR:** Google Drive API (not a local engine)
- **Google Doc:** google-api-python-client + OAuth installed app flow
- **GPU:** CUDA 12/13, cuDNN 9 (from nvidia-* pip packages)

## Files

- `process.py` — main pipeline
- `google_drive_export.py` — Drive/Docs API module (auth, OCR, doc build)
- `process_lecture.bat` — drag-and-drop wrapper for Windows
- `credentials.json` — OAuth client (from Google Cloud Console, not committed)
- `token.json` — OAuth token after first run (not committed)
- `*.transcript.json` — transcript cache (not committed)
- `output/<video_name>/` — local results

## Dependencies

```
# Core
pip install faster-whisper scenedetect[opencv]

# CUDA runtime (required on Windows for GPU)
pip install nvidia-cudnn-cu12

# Google Drive integration
pip install google-auth google-auth-oauthlib google-api-python-client
```

Plus `ffmpeg` in the system PATH.

## Workflow for new lectures

1. Recorded a lecture (Zoom, Meet, OBS — anything)
2. Dropped the mp4 into any folder
3. Dragged it onto `process_lecture.bat`
4. Waited ~15 min
5. Got a Google Doc in Drive/Lectures, ready for NotebookLM

## Plans / todo

- [ ] Merge the two stages into a single run via subprocess isolation of transcribe() (Blackwell crash workaround)
- [ ] Detect screencast vs presentation → different default thresholds
- [ ] Batch processing: drop a folder with N videos → process them one by one
- [ ] Convert notes.md to PDF via pandoc
- [ ] Optional merging of adjacent frames (A/B) when the change was gradual (animated bullet appearance)
