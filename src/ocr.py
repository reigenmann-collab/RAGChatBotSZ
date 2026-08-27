"""
Step 1b - OCR for scanned ordinances.

Four of the five municipal road-traffic Erlasse are image-only scans. Without a
text layer they cannot be retrieved, which is precisely the corpus-completeness
failure mode the PoC identified (report 5.6): a document that is not indexed
does not exist as far as the assistant is concerned.

Each page is extracted as a PNG and transcribed by the Gemini vision model.
Results are cached so a re-run costs nothing. Documents flagged indexable:false
in config.yaml are skipped - OCR of a cadastral map yields parcel labels, not
answerable content.
"""
from __future__ import annotations

import io
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import load_config, path  # noqa: E402
from llm import vision_transcribe  # noqa: E402

CFG = load_config()
OCR_CFG = CFG["ocr"]

PROMPT = """Dies ist die gescannte Seite eines amtlichen Erlasses der Gemeinde Schwyz.

Transkribiere den vollständigen Text dieser Seite wortgetreu auf Deutsch.

Regeln:
- Übernimm Paragraphenzeichen (§), Artikel-, Absatz- und Ziffernnummerierung exakt.
- Behalte die Gliederung bei (Titel, Abschnitte, Absätze, Aufzählungen).
- Gib Tabellen als zeilenweise Werte mit " | " als Trennzeichen wieder.
- Übersetze, kürze, korrigiere und kommentiere nichts.
- Wenn eine Stelle unleserlich ist, schreibe [unleserlich].
- Gib ausschliesslich den transkribierten Text aus, ohne Vor- oder Nachbemerkung."""


def page_images(pdf_bytes: bytes) -> list[bytes]:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    images: list[bytes] = []
    for page in reader.pages:
        for img in page.images:
            images.append(img.data)
            break  # one scan image per page
    return images


def transcribe(png: bytes) -> str:
    return vision_transcribe(
        system=PROMPT,
        image_bytes=png,
        mime_type="image/png",
        max_tokens=OCR_CFG["max_tokens"],
        model=OCR_CFG["model"],
    )


def main() -> None:
    if not OCR_CFG.get("enabled", True):
        print("OCR disabled in config.")
        return

    indexable = {s["id"]: s.get("indexable", True) for s in CFG["corpus"]["sources"]}
    headers = {"User-Agent": CFG["corpus"]["user_agent"]}
    processed = 0

    for raw_file in sorted(path("data", "raw").glob("*.json")):
        if raw_file.name.startswith("_") or raw_file.name.endswith(".ocr.json"):
            continue
        rec = json.loads(raw_file.read_text(encoding="utf-8"))

        if rec["char_count"] >= 200:
            continue
        if not indexable.get(rec["id"], True):
            print(f"  skip  {rec['id']:<28} not indexable (map/plan)")
            continue

        cache = path("data", "raw", f"{rec['id']}.ocr.json")
        if OCR_CFG.get("cache", True) and cache.exists():
            text = json.loads(cache.read_text(encoding="utf-8"))["text"]
            print(f"  cache {rec['id']:<28} {len(text):>7} chars")
        else:
            pdf = requests.get(rec["content_url"], headers=headers, timeout=60).content
            pages = page_images(pdf)
            if not pages:
                print(f"  FAIL  {rec['id']:<28} no page images found")
                continue
            parts = [transcribe(png) for png in pages]
            text = re.sub(r"\n{3,}", "\n\n", "\n\n".join(parts)).strip()
            cache.write_text(
                json.dumps(
                    {
                        "id": rec["id"],
                        "pages": len(pages),
                        "model": OCR_CFG["model"],
                        "ocr_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "text": text,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            print(f"  ocr   {rec['id']:<28} {len(pages)} page(s)  {len(text):>7} chars")

        rec["text"] = text
        rec["char_count"] = len(text)
        rec["text_source"] = "ocr"
        rec["ocr_model"] = OCR_CFG["model"]
        raw_file.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        processed += 1

    print(f"\n{processed} document(s) transcribed or restored from cache.")


if __name__ == "__main__":
    main()
