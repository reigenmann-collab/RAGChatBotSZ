"""
Step 2 - Chunking, embedding and vector index construction.

Embeddings are computed locally with a German/English ONNX model. Nothing about
the corpus or a later citizen query leaves the machine at retrieval time; only
answer generation calls an external API. This keeps the retrieval half of the
pipeline consistent with REQ-07 even in the prototype.

Vectors are L2-normalised and stored in a FAISS inner-product index, which makes
the inner product equal to cosine similarity - the quantity S1 is defined on
(report 4.3).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import faiss
import numpy as np
from fastembed import TextEmbedding

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import load_config, path  # noqa: E402

CFG = load_config()
RET = CFG["retrieval"]


def split_text(text: str, size: int, overlap: int) -> list[str]:
    """Paragraph-aware split. Paragraph boundaries are preferred to mid-sentence
    cuts so that a legal provision stays with its own heading where possible."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 <= size:
            current = f"{current}\n\n{para}" if current else para
            continue
        if current:
            chunks.append(current)
        if len(para) <= size:
            current = para
            continue
        # A single oversized paragraph (long ordinance section) is hard-split.
        start = 0
        while start < len(para):
            chunks.append(para[start : start + size])
            start += size - overlap
        current = ""

    if current:
        chunks.append(current)

    # Re-introduce overlap between adjacent chunks for retrieval continuity.
    if overlap <= 0 or len(chunks) < 2:
        return chunks
    overlapped = [chunks[0]]
    for prev, nxt in zip(chunks, chunks[1:]):
        overlapped.append((prev[-overlap:] + "\n" + nxt).strip())
    return overlapped


def build_chunks() -> list[dict]:
    indexable = {s["id"]: s.get("indexable", True) for s in CFG["corpus"]["sources"]}
    chunks: list[dict] = []
    skipped: list[str] = []

    for raw_file in sorted(path("data", "raw").glob("*.json")):
        if raw_file.name.startswith("_") or raw_file.name.endswith(".ocr.json"):
            continue
        doc = json.loads(raw_file.read_text(encoding="utf-8"))

        if not indexable.get(doc["id"], True):
            skipped.append(f"{doc['id']} (not indexable)")
            continue
        if doc["char_count"] < 200:
            skipped.append(f"{doc['id']} (no usable text - run src/ocr.py)")
            continue

        pieces = split_text(doc["text"], RET["chunk_size_chars"], RET["chunk_overlap_chars"])
        for i, piece in enumerate(pieces):
            chunks.append(
                {
                    "chunk_id": f"{doc['id']}#{i:03d}",
                    "doc_id": doc["id"],
                    "doc_title": doc["title"],
                    "doc_type": doc["doc_type"],
                    "source_url": doc["landing_url"],
                    "content_url": doc["content_url"],
                    "fetched_at": doc["fetched_at"],
                    "text_source": doc.get("text_source", "native"),
                    "text": piece,
                    # Embedded with the document title prefixed. Chunks taken from
                    # the middle of a document otherwise lose all trace of which
                    # document they came from, which cost recall on queries that
                    # name the document ("Gewerbeparkkarte", "Personalparkplatz").
                    "embed_text": f"{doc['title']}\n\n{piece}",
                }
            )
        print(f"  {doc['id']:<28} {doc['doc_type']:<15} {len(pieces):>3} chunks")

    for s in skipped:
        print(f"  skipped: {s}")
    return chunks


def main() -> None:
    chunks = build_chunks()
    if not chunks:
        raise SystemExit("No chunks produced - run src/ingest.py (and src/ocr.py) first.")

    print(f"\nEmbedding {len(chunks)} chunks with {RET['embedding_model']} ...")
    embedder = TextEmbedding(model_name=RET["embedding_model"])
    vectors = np.array(list(embedder.embed([c["embed_text"] for c in chunks])), dtype="float32")
    faiss.normalize_L2(vectors)

    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    faiss.write_index(index, str(path("data", "index", "corpus.faiss")))

    with open(path("data", "index", "chunks.jsonl"), "w", encoding="utf-8") as fh:
        for c in chunks:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")

    doc_types = sorted({c["doc_type"] for c in chunks})
    path("data", "index", "meta.json").write_text(
        json.dumps(
            {
                "embedding_model": RET["embedding_model"],
                "dimension": int(vectors.shape[1]),
                "chunk_count": len(chunks),
                "document_count": len({c["doc_id"] for c in chunks}),
                "doc_types_indexed": doc_types,
                "chunk_size_chars": RET["chunk_size_chars"],
                "chunk_overlap_chars": RET["chunk_overlap_chars"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"Index built: {len(chunks)} chunks, dim {vectors.shape[1]}")
    print(f"Document types indexed: {', '.join(doc_types)}")

    # The coverage check can only fire if the document types it requires exist.
    required = {t for rule in CFG["coverage"]["rules"] for t in rule["required_doc_types"]}
    missing = required - set(doc_types)
    if missing:
        print(f"WARNING: coverage rules require doc_types not present in the index: {sorted(missing)}")


if __name__ == "__main__":
    main()
