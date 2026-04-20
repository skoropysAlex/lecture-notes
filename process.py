"""
Lecture processor: video → markdown notes with slides + transcript.

Usage:
    python process.py path/to/video.mp4
    python process.py path/to/video.mp4 --output-dir ./notes --model large-v3

Output structure:
    output_dir/
        video_name/
            notes.md
            slides/
                slide_001.png
                slide_002.png
                ...
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from datetime import timedelta

# ---------- Dependencies (install once) ----------
# pip install faster-whisper scenedetect[opencv] nvidia-cudnn-cu12
# Also requires ffmpeg in PATH (https://ffmpeg.org/)
# -------------------------------------------------

# --- Make CUDA DLLs from pip-installed nvidia-* packages discoverable on Windows ---
# Without this, ctranslate2 fails with "Library cublas64_12.dll is not found"
if sys.platform == "win32":
    try:
        import site
        registered = []
        for site_dir in site.getsitepackages() + [site.getusersitepackages()]:
            nvidia_root = Path(site_dir) / "nvidia"
            if not nvidia_root.is_dir():
                continue
            for sub in nvidia_root.iterdir():
                bin_dir = sub / "bin"
                if bin_dir.is_dir():
                    os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
                    registered.append(str(bin_dir))
        if registered:
            print(f"[init] Registered {len(registered)} CUDA DLL paths from venv")
        else:
            print("[init] WARNING: No nvidia/*/bin directories found — GPU will likely fail")
    except Exception as e:
        print(f"[warn] Could not register CUDA DLL paths: {e}")

from faster_whisper import WhisperModel
from scenedetect import detect, ContentDetector


# ============================================================
# 1. SCENE DETECTION (slide changes)
# ============================================================

def detect_slide_changes(video_path: Path, threshold: float = 27.0,
                         min_scene_len_sec: float = 5.0) -> list[float]:
    """
    Returns list of timestamps (seconds) where slides change.
    First entry is always 0.0 (the opening slide).
    """
    print(f"[1/4] Detecting slide changes in {video_path.name}...")

    # min_scene_len in scenedetect is in frames; convert from seconds
    # We use a conservative FPS=30 estimate; precise FPS isn't critical here
    min_scene_len_frames = int(min_scene_len_sec * 30)

    scene_list = detect(
        str(video_path),
        ContentDetector(threshold=threshold, min_scene_len=min_scene_len_frames),
    )

    # scene_list is [(start_timecode, end_timecode), ...]
    timestamps = [0.0]
    for start, _end in scene_list:
        ts = start.get_seconds()
        if ts > 0.5:  # skip the very first scene (already 0.0)
            timestamps.append(ts)

    print(f"      Found {len(timestamps)} slides")
    return timestamps


# ============================================================
# 2. EXTRACT SLIDE FRAMES via ffmpeg
# ============================================================

def extract_slide_frames(video_path: Path, timestamps: list[float],
                         slides_dir: Path) -> list[Path]:
    """
    For each timestamp, grab one frame ~1 second after the change
    (to skip transition animations).
    """
    print(f"[2/4] Extracting {len(timestamps)} slide frames...")
    slides_dir.mkdir(parents=True, exist_ok=True)

    frame_paths = []
    for i, ts in enumerate(timestamps, start=1):
        # offset by 1s to land past any transition
        grab_time = ts + 1.0
        out_path = slides_dir / f"slide_{i:03d}.png"

        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", f"{grab_time:.2f}",
            "-i", str(video_path),
            "-frames:v", "1",
            "-q:v", "2",
            str(out_path),
        ]
        subprocess.run(cmd, check=True)
        frame_paths.append(out_path)

    return frame_paths


# ============================================================
# 3. TRANSCRIBE with faster-whisper
# ============================================================

def detect_language_first(video_path: Path, model_size: str,
                          sample_seconds: int = 30) -> tuple[str, float]:
    """
    Quick language detection on the first N seconds of audio.
    Returns (language_code, confidence) — e.g. ('uk', 0.98).

    Runs whisper with language=None but stops after first segment so we spend
    only a few seconds on detection. The main transcription happens later
    with the confirmed language.
    """
    print(f"[0/4] Detecting language from first {sample_seconds}s of audio...")

    try:
        model = WhisperModel(model_size, device="cuda", compute_type="float16")
    except Exception:
        model = WhisperModel(model_size, device="cpu", compute_type="int8")

    # We only need language detection, not full transcription of the sample.
    # faster-whisper detects language as part of transcribe() setup and
    # exposes it via info.language *before* iterating segments.
    segments, info = model.transcribe(
        str(video_path),
        language=None,  # auto-detect
        vad_filter=True,
        beam_size=1,  # fast
        without_timestamps=True,
    )
    # Consume only the first segment to ensure info is populated, then stop
    try:
        next(iter(segments))
    except StopIteration:
        pass

    detected = info.language
    confidence = info.language_probability

    # Cleanup before we return (same Blackwell precaution)
    del model
    import gc
    gc.collect()

    print(f"      Detected: {detected} (confidence: {confidence:.0%})")
    return detected, confidence


def confirm_language(detected: str, confidence: float) -> str:
    """
    Ask user to confirm the detected language or pick another.
    Returns the final language code to use.
    """
    COMMON = {
        "uk": "Українська",
        "en": "English",
        "ru": "Русский",
        "pl": "Polski",
        "de": "Deutsch",
        "es": "Español",
        "fr": "Français",
    }
    detected_name = COMMON.get(detected, detected)

    # High confidence + known language → auto-accept without prompting
    if confidence >= 0.90 and detected in COMMON:
        print(f"      Using detected language: {detected} ({detected_name})")
        return detected

    # Low confidence OR unusual language → ask
    print()
    print(f"      Detected: {detected} ({detected_name}) at {confidence:.0%} confidence")
    print("      Options:")
    print(f"        [Enter] Use {detected}")
    print("        uk, en, ru, pl, de, es, fr — force this language")
    print("        (any other whisper code also works)")
    choice = input("      Your choice: ").strip().lower()

    if not choice:
        return detected
    return choice


def transcribe(video_path: Path, model_size: str,
               language: str = "uk") -> tuple[list[dict], float, str]:
    """
    Returns (segments, duration, detected_language).
    Pass language="auto" to let whisper detect automatically.
    """
    whisper_lang = None if language == "auto" else language
    lang_label = "auto-detect" if whisper_lang is None else language
    print(f"[3/4] Transcribing audio (model={model_size}, lang={lang_label})...")
    print(f"      First run will download the {model_size} model")

    # Auto-pick GPU if available, fallback to CPU
    try:
        model = WhisperModel(model_size, device="cuda", compute_type="float16")
    except Exception:
        print("      GPU unavailable, falling back to CPU (will be slow)")
        model = WhisperModel(model_size, device="cpu", compute_type="int8")

    segments, info = model.transcribe(
        str(video_path),
        language=whisper_lang,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
        beam_size=5,
    )

    # When whisper auto-detects, info.language contains the detected code
    detected_lang = info.language
    if whisper_lang is None:
        print(f"      Detected language: {detected_lang} "
              f"(confidence: {info.language_probability:.0%})")

    result = []
    for seg in segments:
        result.append({
            "start": seg.start,
            "end": seg.end,
            "text": seg.text.strip(),
        })
        # live progress
        print(f"      [{format_ts(seg.start)}] {seg.text.strip()[:80]}")

    print(f"      Got {len(result)} segments, total duration: {format_ts(info.duration)}")

    # CRITICAL: persist transcript to disk immediately. On some Windows + CUDA 13
    # + Blackwell (RTX 50xx) combos, ctranslate2 crashes the Python process
    # during teardown. By dumping to JSON right here, we guarantee the
    # expensive transcription work isn't lost even if the process dies below.
    import json
    cache_path = Path(f"{video_path.stem}.transcript.json")
    cache_path.write_text(
        json.dumps({
            "segments": result,
            "duration": info.duration,
            "language": detected_lang,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"      Cached transcript to {cache_path}")

    # Explicit cleanup — on Windows some ctranslate2 versions crash Python
    # during GC of CUDA resources if we don't release model explicitly here.
    del model
    import gc
    gc.collect()

    return result, info.duration, detected_lang


# ============================================================
# 4. MERGE: assign transcript segments to slides
# ============================================================

def build_markdown(video_name: str, slide_timestamps: list[float],
                   slide_frames: list[Path], segments: list[dict],
                   total_duration: float) -> str:
    """
    For each slide, collect transcript segments that fall within
    [slide_start, next_slide_start).
    """
    print("[4/4] Building markdown notes...")

    lines = [f"# {video_name}\n"]

    # build slide intervals
    intervals = []
    for i, ts in enumerate(slide_timestamps):
        end_ts = slide_timestamps[i + 1] if i + 1 < len(slide_timestamps) else total_duration
        intervals.append((ts, end_ts))

    for i, ((start, end), frame_path) in enumerate(zip(intervals, slide_frames), start=1):
        # collect segments whose midpoint falls in this slide's interval
        slide_segments = [
            s for s in segments
            if start <= (s["start"] + s["end"]) / 2 < end
        ]

        lines.append(f"\n## Slide {i} — {format_ts(start)}\n")
        # relative path so the folder stays portable
        lines.append(f"![Slide {i}](slides/{frame_path.name})\n")

        if slide_segments:
            lines.append("")
            for s in slide_segments:
                lines.append(f"**[{format_ts(s['start'])}]** {s['text']}")
                lines.append("")
        else:
            lines.append("\n_(no speech during this slide)_\n")

    return "\n".join(lines)


def build_notebooklm_text(video_name: str, slide_timestamps: list[float],
                          slide_frames: list[Path], segments: list[dict],
                          total_duration: float) -> str:
    """
    NotebookLM-friendly version: no images, clean structure.
    Each slide section has a clear header and the spoken transcript underneath.
    Pair this with a Google Doc containing OCR'd slides for full coverage.
    """
    lines = [
        f"# {video_name}",
        "",
        f"Загальна тривалість: {format_ts(total_duration)}",
        f"Кількість слайдів: {len(slide_timestamps)}",
        "",
        "---",
        "",
    ]

    intervals = []
    for i, ts in enumerate(slide_timestamps):
        end_ts = slide_timestamps[i + 1] if i + 1 < len(slide_timestamps) else total_duration
        intervals.append((ts, end_ts))

    for i, ((start, end), frame_path) in enumerate(zip(intervals, slide_frames), start=1):
        slide_segments = [
            s for s in segments
            if start <= (s["start"] + s["end"]) / 2 < end
        ]

        # Header with time range — helps NotebookLM understand the context
        lines.append(f"## Слайд {i} ({format_ts(start)} – {format_ts(end)})")
        lines.append("")
        lines.append(f"_Зображення слайда: {frame_path.name}_")
        lines.append("")

        if slide_segments:
            lines.append("**Розповідь:**")
            lines.append("")
            # Glue segments into flowing paragraphs (no per-line timestamps —
            # NotebookLM works better with prose than with timestamped lists)
            paragraph = " ".join(s["text"] for s in slide_segments)
            lines.append(paragraph)
        else:
            lines.append("_(тиша / без коментарів лектора)_")

        lines.append("")
        lines.append("")

    return "\n".join(lines)


# ============================================================
# Helpers
# ============================================================

def format_ts(seconds: float) -> str:
    """Format seconds as HH:MM:SS."""
    return str(timedelta(seconds=int(seconds)))


def get_video_duration(video_path: Path) -> float:
    """Use ffprobe to get duration in seconds."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    out = subprocess.check_output(cmd).decode().strip()
    return float(out)


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path, help="Path to video file")
    parser.add_argument("--output-dir", type=Path, default=Path("./output"),
                        help="Where to put the result folder (default: ./output)")
    parser.add_argument("--model", default="large-v3",
                        help="faster-whisper model size (default: large-v3)")
    parser.add_argument("--language", default="auto",
                        help="Audio language code: auto (detect), uk, en, ru, pl, "
                             "or any whisper-supported code (default: auto). "
                             "For mixed-language content (surzhyk) try 'uk' or 'ru' "
                             "explicitly — auto-detect may switch between segments.")
    parser.add_argument("--no-confirm-language", action="store_true",
                        help="Skip the interactive language confirmation prompt. "
                             "Useful for batch/scripted runs. When --language=auto and "
                             "this flag is set, whisper's detected language is used "
                             "without asking.")
    parser.add_argument("--scene-threshold", type=float, default=18.0,
                        help="Scene change sensitivity, lower = more sensitive (default: 18, "
                             "tuned for screencasts with overlay webcam windows)")
    parser.add_argument("--min-slide-duration", type=float, default=5.0,
                        help="Minimum seconds between slide changes (default: 5)")
    parser.add_argument("--google-doc", action="store_true",
                        help="Also upload to Google Drive: create a Google Doc with "
                             "OCR'd slides + transcript. Requires credentials.json in cwd.")
    parser.add_argument("--gdrive-parent-folder", default="Lectures",
                        help="Name of the Google Drive folder where all docs are saved "
                             "(default: Lectures). Created automatically if missing.")
    args = parser.parse_args()

    if not args.video.exists():
        sys.exit(f"Error: {args.video} not found")

    # prepare output folder
    work_dir = args.output_dir / args.video.stem
    slides_dir = work_dir / "slides"
    work_dir.mkdir(parents=True, exist_ok=True)

    # pipeline
    timestamps = detect_slide_changes(
        args.video,
        threshold=args.scene_threshold,
        min_scene_len_sec=args.min_slide_duration,
    )
    frames = extract_slide_frames(args.video, timestamps, slides_dir)

    # Check for cached transcript — skip the expensive GPU step if we already have it.
    # This also makes the script resumable if transcription succeeded but later
    # steps crashed (known issue with ctranslate2 + CUDA 13 + Blackwell GPUs).
    import json
    cache_path = Path(f"{args.video.stem}.transcript.json")
    if cache_path.exists():
        print(f"[3/4] Using cached transcript from {cache_path}")
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        segments = cached["segments"]
        duration = cached["duration"]
        detected_lang = cached.get("language", args.language if args.language != "auto" else "uk")
    else:
        # Language confirmation step: if user asked for auto, detect first
        # and let them confirm or override. For explicit codes (uk/en/ru/...)
        # we skip the prompt.
        effective_language = args.language
        if args.language == "auto" and not args.no_confirm_language:
            detected, confidence = detect_language_first(args.video, args.model)
            effective_language = confirm_language(detected, confidence)

        segments, duration, detected_lang = transcribe(
            args.video, model_size=args.model, language=effective_language
        )
    md = build_markdown(args.video.stem, timestamps, frames, segments, duration)
    notes_path = work_dir / "notes.md"
    notes_path.write_text(md, encoding="utf-8")

    nlm_text = build_notebooklm_text(args.video.stem, timestamps, frames, segments, duration)
    nlm_path = work_dir / "notes_for_notebooklm.md"
    nlm_path.write_text(nlm_text, encoding="utf-8")

    print(f"\n✓ Done.")
    print(f"  Visual notes (with slides): {notes_path}")
    print(f"  NotebookLM text:            {nlm_path}")
    print(f"  Slides folder:              {slides_dir}")

    # ---- Optional: upload to Google Drive as a single Google Doc ----
    if args.google_doc:
        print("\n[5/5] Exporting to Google Drive...")
        from google_drive_export import (
            get_services, ocr_image, find_or_create_folder, build_google_doc,
        )

        cwd = Path.cwd()
        credentials_path = cwd / "credentials.json"
        token_path = cwd / "token.json"

        try:
            drive, docs = get_services(credentials_path, token_path)
        except FileNotFoundError as e:
            print(f"      [error] {e}")
            return

        # Use a persistent parent folder so all lectures end up in one place.
        # Find or create "Lectures" at Drive root.
        parent_folder_name = args.gdrive_parent_folder
        folder_id = find_or_create_folder(drive, parent_folder_name, parent_id=None)
        print(f"      Using Drive folder: {parent_folder_name}")

        # Build the doc title: "YYYY-MM-DD — <video stem>"
        from datetime import date
        doc_title = f"{date.today().isoformat()} — {args.video.stem}"

        # OCR each slide
        print(f"      Running OCR on {len(frames)} slides via Drive...")
        slide_data = []
        intervals = []
        for i, ts in enumerate(timestamps):
            end_ts = timestamps[i + 1] if i + 1 < len(timestamps) else duration
            intervals.append((ts, end_ts))

        for i, ((start, end), frame_path) in enumerate(zip(intervals, frames), start=1):
            print(f"      OCR slide {i}/{len(frames)}...", end="\r")
            try:
                # Use detected/specified language for OCR hint. Google Drive handles
                # mixed-language content (e.g. UA text + EN technical terms) regardless.
                ocr_text = ocr_image(drive, frame_path, language_hint=detected_lang)
            except Exception as e:
                print(f"\n      [warn] OCR failed for slide {i}: {e}")
                ocr_text = ""

            slide_segments = [
                s for s in segments
                if start <= (s["start"] + s["end"]) / 2 < end
            ]
            transcript = " ".join(s["text"] for s in slide_segments)

            slide_data.append({
                "index": i,
                "image_path": frame_path,
                "ocr": ocr_text,
                "transcript": transcript,
                "start": format_ts(start),
                "end": format_ts(end),
            })

        print(f"      OCR complete for {len(slide_data)} slides.        ")

        # Build the doc
        doc_id, doc_url = build_google_doc(
            drive, docs, title=doc_title,
            slides=slide_data, folder_id=folder_id,
        )
        print(f"\n  Google Doc:                 {doc_url}")
        print(f"  Title:                      {doc_title}")


if __name__ == "__main__":
    import traceback
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
