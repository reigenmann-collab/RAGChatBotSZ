"""Step 3 - Retrieval. Loads the FAISS index once and serves top-k lookups."""
from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path

import faiss
import numpy as np
from fastembed import TextEmbedding

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import load_config, path  # noqa: E402

CFG = load_config()
RET = CFG["retrieval"]


@lru_cache(maxsize=1)
def _resources():
    index_file = path("data", "index", "corpus.faiss")
    if not index_file.exists():
        raise RuntimeError("No index found. Run src/ingest.py then src/chunk_index.py.")
    index = faiss.read_index(str(index_file))
    with open(path("data", "index", "chunks.jsonl"), encoding="utf-8") as fh:
        chunks = [json.loads(line) for line in fh]
    embedder = TextEmbedding(model_name=RET["embedding_model"])
    return index, chunks, embedder


def embed_query(text: str) -> np.ndarray:
    _, _, embedder = _resources()
    vec = np.array(list(embedder.embed([text])), dtype="float32")
    faiss.normalize_L2(vec)
    return vec


def retrieve(query: str, top_k: int | None = None) -> list[dict]:
    """Return the top-k chunks, each with its cosine similarity to the query."""
    index, chunks, _ = _resources()
    k = top_k or RET["top_k"]
    scores, ids = index.search(embed_query(query), min(k, index.ntotal))

    hits: list[dict] = []
    for score, idx in zip(scores[0], ids[0]):
        if idx < 0:
            continue
        hit = dict(chunks[idx])
        hit.pop("embed_text", None)
        hit["similarity"] = float(score)
        hits.append(hit)
    return hits


def index_stats() -> dict:
    return json.loads(path("data", "index", "meta.json").read_text(encoding="utf-8"))
