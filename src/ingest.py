"""
Step 1 - Corpus ingestion.

Fetches the Gemeinde Schwyz road-traffic / parking corpus defined in config.yaml
and writes one JSON record per document to data/raw/.

Three source kinds:
  web    - an HTML content page; main content plus tables are extracted
  doc    - a /_doc/<id> URL that redirects to a PDF
  erlass - an ordinance landing page whose body links to the ordinance PDF

Every record carries the metadata the pipeline needs downstream: the doc_type
that drives the REQ-11 coverage check, the source URL for citation, and a
fetch timestamp plus content hash so corpus currency is auditable (report 2.4).
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import sys
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from config import load_config, path  # noqa: E402

CFG = load_config()
CORPUS = CFG["corpus"]
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": CORPUS["user_agent"]})

BOILERPLATE = re.compile(
    r"^(Zum Inhalt springen|Suche|Menü|Navigation|Teilen|Drucken|Kontakt aufnehmen)$",
    re.I,
)


def _fetch(url: str) -> requests.Response:
    time.sleep(CORPUS["request_delay_seconds"])
    resp = SESSION.get(url, timeout=45)
    resp.raise_for_status()
    return resp


def _table_to_text(table) -> str:
    """Render an HTML table as pipe-delimited rows.

    The parking tariffs live in a table, so losing table structure would lose
    the fee schedule - exactly the corpus-completeness failure the PoC found.
    """
    lines = []
    for tr in table.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
        if any(cells):
            lines.append(" | ".join(cells))
    return "\n".join(lines)


def _extract_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form", "noscript"]):
        tag.decompose()

    # The i-web CMS renders the site chrome inside the content column: a login
    # overlay, a quick-search panel, the breadcrumb dropdowns and the address
    # block. Left in, they add ~2,600 characters of identical text to every page,
    # which drags unrelated chunks toward each other and dilutes retrieval.
    for selector in (
        ".banner-container",
        ".breadcrumb-outer",
        ".mobile-nav",
        ".quicksearch",
        ".login-container",
        "#icms-toc-container",
    ):
        for tag in soup.select(selector):
            tag.decompose()

    main = (
        soup.select_one(".content-container")
        or soup.select_one(".main-outercon")
        or soup.select_one("main")
        or soup.body
    )
    if main is None:
        return ""

    parts: list[str] = []
    for table in main.find_all("table"):
        rendered = _table_to_text(table)
        if rendered:
            parts.append("[TABELLE]\n" + rendered + "\n[/TABELLE]")
        table.decompose()

    body = main.get_text("\n", strip=True)
    body = "\n".join(
        ln for ln in (l.strip() for l in body.splitlines()) if ln and not BOILERPLATE.match(ln)
    )
    return "\n\n".join([body] + parts).strip()


def _extract_pdf(raw: bytes) -> str:
    reader = PdfReader(io.BytesIO(raw))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    text = "\n".join(pages)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _resolve_erlass_pdf(landing_url: str) -> str | None:
    """Ordinance landing pages carry the PDF as a /_doc/<id> link in the body."""
    resp = _fetch(landing_url)
    soup = BeautifulSoup(resp.text, "html.parser")
    for a in soup.select('a[href^="/_doc/"]'):
        return CORPUS["base_url"] + a["href"]
    return None


def ingest_source(src: dict) -> dict:
    kind, url = src["kind"], src["url"]
    pdf_url = None

    if kind == "web":
        resp = _fetch(url)
        text, content_url = _extract_html(resp.text), url
    else:
        if kind == "erlass":
            pdf_url = _resolve_erlass_pdf(url)
            if not pdf_url:
                raise RuntimeError(f"no PDF link found on {url}")
        else:
            pdf_url = url
        resp = _fetch(pdf_url)
        text, content_url = _extract_pdf(resp.content), resp.url

    return {
        "id": src["id"],
        "title": src["title"],
        "doc_type": src["doc_type"],
        "kind": kind,
        "landing_url": url,
        "content_url": content_url,
        "note": src.get("note", ""),
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "char_count": len(text),
        "text": text,
    }


def main() -> None:
    results, failures = [], []
    for src in CORPUS["sources"]:
        try:
            rec = ingest_source(src)
        except Exception as exc:  # noqa: BLE001 - report, do not abort the run
            failures.append((src["id"], repr(exc)))
            print(f"  FAIL  {src['id']:<28} {exc}")
            continue

        out = path("data", "raw", f"{rec['id']}.json")
        out.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        results.append(rec)
        flag = "  <-- NO TEXT" if rec["char_count"] < 200 else ""
        print(f"  ok    {rec['id']:<28} {rec['doc_type']:<15} {rec['char_count']:>7} chars{flag}")

    print(f"\n{len(results)} document(s) ingested, {len(failures)} failed.")
    empty = [r["id"] for r in results if r["char_count"] < 200]
    if empty:
        print(f"Documents with no usable text (corpus gap, see REQ-11): {', '.join(empty)}")

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "documents": [{k: v for k, v in r.items() if k != "text"} for r in results],
        "failures": failures,
        "empty_documents": empty,
    }
    path("data", "raw", "_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
