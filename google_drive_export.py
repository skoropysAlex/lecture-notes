"""
Google Drive integration: upload slide images with OCR, then build a single
Google Doc combining slide images, OCR'd text from each slide, and the
spoken transcript per slide.

Auth: needs `credentials.json` (OAuth Desktop client) in the working directory.
First run opens a browser for consent and writes `token.json` for future runs.
"""

from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Iterable

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload


# Drive scope is sufficient — Docs API uses the same OAuth scope umbrella when
# we only export documents. Adding docs scope explicitly to be safe.
SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
]


# ============================================================
# Auth
# ============================================================

def get_services(credentials_path: Path, token_path: Path):
    """
    Returns (drive_service, docs_service). Triggers browser auth on first run.
    """
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not credentials_path.exists():
                raise FileNotFoundError(
                    f"OAuth credentials not found at {credentials_path}. "
                    "Download from Google Cloud Console and place there."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_path), SCOPES
            )
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    docs = build("docs", "v1", credentials=creds, cache_discovery=False)
    return drive, docs


# ============================================================
# OCR via Drive: upload image, convert to Google Doc, read text, delete temp
# ============================================================

def ocr_image(drive, image_path: Path, language_hint: str = "uk") -> str:
    """
    Uploads an image to Drive with conversion to Google Doc — this triggers
    OCR. Reads the resulting text, then deletes the temp document.
    """
    media = MediaFileUpload(str(image_path), mimetype="image/png", resumable=False)
    file_meta = {
        "name": f"_ocr_temp_{image_path.stem}",
        "mimeType": "application/vnd.google-apps.document",
    }
    # ocrLanguage parameter improves recognition for non-English content
    created = drive.files().create(
        body=file_meta,
        media_body=media,
        ocrLanguage=language_hint,
        fields="id",
    ).execute()
    file_id = created["id"]

    try:
        # Export the resulting Doc as plain text
        request = drive.files().export_media(fileId=file_id, mimeType="text/plain")
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        text = buf.getvalue().decode("utf-8", errors="replace").strip()

        # Drive's OCR puts the original image at the top of the doc, then OCR text.
        # When exported as plain text, the image is gone — only text remains.
        # Sometimes there's a leading title line (the file name) — strip it.
        lines = text.splitlines()
        if lines and lines[0].startswith("_ocr_temp_"):
            lines = lines[1:]
        return "\n".join(lines).strip()
    finally:
        # Clean up: don't leave OCR junk in user's Drive
        try:
            drive.files().delete(fileId=file_id).execute()
        except HttpError:
            pass


# ============================================================
# Build the final Google Doc
# ============================================================

def upload_image_to_drive(drive, image_path: Path, parent_folder_id: str) -> str:
    """Uploads an image as a regular file (no conversion). Returns file ID."""
    media = MediaFileUpload(str(image_path), mimetype="image/png", resumable=False)
    file_meta = {
        "name": image_path.name,
        "parents": [parent_folder_id],
    }
    created = drive.files().create(
        body=file_meta, media_body=media, fields="id"
    ).execute()
    # Make it readable by anyone with the link — needed for embedding into Docs
    drive.permissions().create(
        fileId=created["id"],
        body={"role": "reader", "type": "anyone"},
    ).execute()
    return created["id"]


def create_drive_folder(drive, name: str, parent_id: str | None = None) -> str:
    """Creates a folder in Drive and returns its ID."""
    body = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        body["parents"] = [parent_id]
    folder = drive.files().create(body=body, fields="id").execute()
    return folder["id"]


def find_or_create_folder(drive, name: str, parent_id: str | None = None) -> str:
    """
    Finds a folder by name (optionally under a specific parent). If missing,
    creates it. Returns folder ID. Reusing the same folder across runs keeps
    the user's Drive organized in one place.
    """
    # Build search query
    query_parts = [
        f"name = '{name}'",
        "mimeType = 'application/vnd.google-apps.folder'",
        "trashed = false",
    ]
    if parent_id:
        query_parts.append(f"'{parent_id}' in parents")
    query = " and ".join(query_parts)

    results = drive.files().list(
        q=query, spaces="drive", fields="files(id, name)", pageSize=1
    ).execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]

    # Not found — create it
    return create_drive_folder(drive, name, parent_id)


def build_google_doc(drive, docs, title: str,
                     slides: list[dict], folder_id: str) -> tuple[str, str]:
    """
    slides: [{"index": 1, "image_path": Path, "ocr": str, "transcript": str,
              "start": "0:00:30", "end": "0:01:24"}]

    Returns (doc_id, doc_url).
    """
    # 1. Create empty doc inside the project folder
    doc = docs.documents().create(body={"title": title}).execute()
    doc_id = doc["documentId"]
    # Move to our folder (Docs API creates in root by default)
    drive.files().update(
        fileId=doc_id,
        addParents=folder_id,
        removeParents="root",
        fields="id, parents",
    ).execute()

    # 2. Upload all slide images first (Docs needs URLs to insert images)
    print(f"      Uploading {len(slides)} slide images to Drive...")
    image_urls = {}
    for s in slides:
        img_id = upload_image_to_drive(drive, s["image_path"], folder_id)
        # Direct download link works for inlineImage
        image_urls[s["index"]] = f"https://drive.google.com/uc?id={img_id}&export=download"

    # 3. Build batchUpdate requests — insert content from end to start
    # Working from end to start is easier because indices don't shift backward.
    # But here we build text first, then insert images.
    #
    # Simpler approach: build the whole text, insert it once, then insert images
    # at known positions. We'll use a marker-based approach instead.

    # Build the doc text with placeholders for images
    body_parts = []
    body_parts.append(f"{title}\n\n")

    image_anchors = []  # (text_position, image_url)

    for s in slides:
        slide_header = f"Слайд {s['index']} ({s['start']} – {s['end']})\n"
        body_parts.append(slide_header)

        # Anchor for image goes right after header
        # Position will be calculated after we know where this slide starts
        image_anchors.append({
            "slide_index": s["index"],
            "after_text": slide_header,
            "url": image_urls[s["index"]],
        })

        body_parts.append("\n")  # blank line for image

        if s["ocr"]:
            body_parts.append("Текст зі слайда:\n")
            body_parts.append(s["ocr"] + "\n\n")

        if s["transcript"]:
            body_parts.append("Розповідь:\n")
            body_parts.append(s["transcript"] + "\n\n")
        else:
            body_parts.append("(тиша)\n\n")

    full_text = "".join(body_parts)

    # 4. Insert all text first
    docs.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": [{"insertText": {"location": {"index": 1}, "text": full_text}}]},
    ).execute()

    # 5. Now find positions for images and insert them
    # Re-fetch the document to get clean indices
    image_requests = []
    cursor = 1  # Docs body starts at index 1
    cursor += len(f"{title}\n\n")

    for s, anchor in zip(slides, image_anchors):
        slide_header_len = len(f"Слайд {s['index']} ({s['start']} – {s['end']})\n")
        # Position after the slide header (where blank line is)
        image_pos = cursor + slide_header_len
        image_requests.append({
            "insertInlineImage": {
                "location": {"index": image_pos},
                "uri": anchor["url"],
                "objectSize": {
                    "height": {"magnitude": 240, "unit": "PT"},
                    "width": {"magnitude": 480, "unit": "PT"},
                },
            }
        })

        # Advance cursor past everything in this slide section
        section_len = slide_header_len + 1  # +1 for the blank line/image
        if s["ocr"]:
            section_len += len("Текст зі слайда:\n") + len(s["ocr"] + "\n\n")
        if s["transcript"]:
            section_len += len("Розповідь:\n") + len(s["transcript"] + "\n\n")
        else:
            section_len += len("(тиша)\n\n")
        cursor += section_len

    # Insert images from end to start so indices don't shift
    if image_requests:
        # Reverse the order: highest index first
        image_requests.sort(key=lambda r: -r["insertInlineImage"]["location"]["index"])
        # Send in batches of 10 to avoid request size limits
        BATCH = 10
        for i in range(0, len(image_requests), BATCH):
            chunk = image_requests[i:i + BATCH]
            try:
                docs.documents().batchUpdate(
                    documentId=doc_id, body={"requests": chunk}
                ).execute()
            except HttpError as e:
                print(f"      [warn] Image batch {i}-{i+BATCH} failed: {e}")

    doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
    return doc_id, doc_url
