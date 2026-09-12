"""
ingest.py
Turns everything in corpus/ into a flat list of page/section records
stored in data/chunks.json:

    {doc_id, doc_name, doc_type, page_number, text, image_path}

Run:  python ingest.py
"""

import json
import time
from pathlib import Path

import pymupdf
from pptx import Presentation
from google import genai
from google.genai import types

from config import GEMINI_API_KEY, GEMINI_MODEL


GEMINI_CLIENT = genai.Client(api_key=GEMINI_API_KEY)

CORPUS_DIR = Path("corpus")
IMG_DIR = Path("data/page_images")
IMG_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH = Path("data/chunks.json")

MIN_TEXT_LEN_FOR_PAGE = 40  # below this, treat page as image-heavy


def transcribe_handwritten(image_path: Path) -> str:
    """Send a handwritten photo to Gemini vision for transcription."""
    with open(image_path, "rb") as f:
        img_bytes = f.read()

    prompt = (
        "Transcribe this handwritten page as accurately as possible. "
        "Preserve structure (bullets, arrows, diagrams-as-text, headings). "
        "Mark any word or phrase you are not fully confident about with "
        "[unclear: your best guess]. Do not summarize or clean up the "
        "content -- transcribe exactly what is written, including if it "
        "looks messy or partial."
    )

    mime = "image/jpeg" if image_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"

    response = GEMINI_CLIENT.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            prompt,
            types.Part.from_bytes(data=img_bytes, mime_type=mime),
        ],
    )
    time.sleep(1.5)  # stay under free-tier rate limits
    return response.text.strip()


def describe_visual_page(image_path: Path) -> str:
    """For pages with diagrams/tables/equations: ask Gemini to describe
    the content in enough structured detail to be searchable and answerable."""
    with open(image_path, "rb") as f:
        img_bytes = f.read()

    prompt = (
        "This page contains a diagram, table, or equation from a lecture. "
        "Describe its content in detailed, structured text: list every "
        "label, axis, step, row/column, or symbol you can see, and explain "
        "the relationships shown. Be thorough enough that someone could "
        "answer exam questions about this page from your description alone."
    )
    response = GEMINI_CLIENT.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            prompt,
            types.Part.from_bytes(data=img_bytes, mime_type="image/png"),
        ],
    )
    time.sleep(1.5)
    return response.text.strip()


def ingest_pdfs():
    records = []
    for pdf_path in sorted(CORPUS_DIR.glob("pdfs/*.pdf")):
        doc = pymupdf.open(pdf_path)
        doc_name = pdf_path.name
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text().strip()

            # Always render the page image -- needed for citation display
            # and as a fallback for image-heavy pages.
            pix = page.get_pixmap(dpi=150)
            img_path = IMG_DIR / f"{pdf_path.stem}_p{page_num + 1}.png"
            pix.save(img_path)

            if len(text) < MIN_TEXT_LEN_FOR_PAGE:
                # Likely a diagram/scan-heavy page -- describe it visually.
                print(f"[visual] {doc_name} p.{page_num + 1} (sparse text, describing image)")
                text = describe_visual_page(img_path)

            records.append({
                "doc_id": f"{pdf_path.stem}",
                "doc_name": doc_name,
                "doc_type": "pdf",
                "page_number": page_num + 1,
                "text": text,
                "image_path": str(img_path),
            })
        print(f"Ingested {doc_name}: {len(doc)} pages")
    return records


def ingest_slides():
    records = []
    for pptx_path in sorted(CORPUS_DIR.glob("slides/*.pptx")):
        prs = Presentation(pptx_path)
        doc_name = pptx_path.name
        for i, slide in enumerate(prs.slides):
            texts = []
            for shape in slide.shapes:
                if shape.has_text_frame:
                    texts.append(shape.text_frame.text)
                if shape.has_table:
                    for row in shape.table.rows:
                        texts.append(" | ".join(c.text for c in row.cells))
            # speaker notes
            if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
                notes = slide.notes_slide.notes_text_frame.text
                if notes.strip():
                    texts.append(f"[Speaker notes]: {notes}")

            full_text = "\n".join(t for t in texts if t.strip())

            records.append({
                "doc_id": f"{pptx_path.stem}",
                "doc_name": doc_name,
                "doc_type": "slides",
                "page_number": i + 1,
                "text": full_text if full_text.strip() else "[No extractable text -- likely image-only slide]",
                "image_path": None,
            })
        print(f"Ingested {doc_name}: {len(prs.slides)} slides")
    return records


def ingest_notes():
    records = []
    for note_path in sorted(list(CORPUS_DIR.glob("notes/*.md")) + list(CORPUS_DIR.glob("notes/*.txt"))):
        text = note_path.read_text(encoding="utf-8", errors="ignore")
        # split on markdown headers, else fixed-size chunks
        sections = []
        current = []
        for line in text.splitlines():
            if line.strip().startswith("#") and current:
                sections.append("\n".join(current))
                current = [line]
            else:
                current.append(line)
        if current:
            sections.append("\n".join(current))
        if not sections:
            sections = [text]

        for i, section in enumerate(sections):
            if not section.strip():
                continue
            records.append({
                "doc_id": f"{note_path.stem}",
                "doc_name": note_path.name,
                "doc_type": "notes",
                "page_number": i + 1,  # "page" = section number for notes
                "text": section.strip(),
                "image_path": None,
            })
        print(f"Ingested {note_path.name}: {len(sections)} sections")
    return records


def ingest_handwritten():
    records = []
    exts = ("*.jpg", "*.jpeg", "*.png")
    files = []
    for ext in exts:
        files.extend(CORPUS_DIR.glob(f"handwritten/{ext}"))
    for i, img_path in enumerate(sorted(files)):
        print(f"[handwritten] Transcribing {img_path.name} ...")
        transcription = transcribe_handwritten(img_path)
        records.append({
            "doc_id": f"handwritten_{img_path.stem}",
            "doc_name": f"Handwritten notes - {img_path.name}",
            "doc_type": "handwritten",
            "page_number": i + 1,
            "text": transcription,
            "image_path": str(img_path),
        })
        print(f"    -> {len(transcription)} chars transcribed")
    return records


def main():
    all_records = []
    print("== PDFs ==")
    all_records += ingest_pdfs()
    print("\n== Slides ==")
    all_records += ingest_slides()
    print("\n== Notes (md/txt) ==")
    all_records += ingest_notes()
    print("\n== Handwritten photos ==")
    all_records += ingest_handwritten()

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_records, f, indent=2, ensure_ascii=False)

    print(f"\nDone. {len(all_records)} page/section records written to {OUT_PATH}")
    print("IMPORTANT: manually skim the 'handwritten' entries in chunks.json")
    print("to sanity-check transcription quality before indexing.")


if __name__ == "__main__":
    main()
