"""
Report v4.3 §4.2/§4.3 - Embedding-based topic match for legal/sensitive queries.

Replaces the prototype's first implementation (a keyword list, archived in
docs/PM4_Stichwortlisten_Themenabgleich_REQ11.xlsx). A query is "hard routed"
if its cosine similarity to the NEAREST reference example in
config.yaml -> routing.legal_sensitive_examples is at or above
legal_sensitive_similarity_threshold.

Deliberately takes a precomputed query embedding rather than the raw query
text: the report requires this to run "parallel und ohne zusätzlichen
Modellaufruf" to the retrieval embedding (§4.1), i.e. the SAME vector that
retrieve.embed_query() produces for the vector search is reused here. Embed
the query once in pipeline.py and pass the vector to both.
"""
from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
from fastembed import TextEmbedding

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import load_config  # noqa: E402

CFG = load_config()
ROUTE = CFG["routing"]


@lru_cache(maxsize=1)
def _reference_vectors() -> tuple[np.ndarray, list[str]]:
    """Embed the curated reference examples once per process. Cheap: a few
    dozen short strings through the same local ONNX model used for retrieval -
    no API call, well under a second."""
    examples = ROUTE["legal_sensitive_examples"]
    embedder = TextEmbedding(model_name=CFG["retrieval"]["embedding_model"])
    vecs = np.array(list(embedder.embed(examples)), dtype="float32")
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    return vecs, examples


def nearest_match(query_vec: np.ndarray) -> dict:
    """query_vec: the (1, dim) L2-normalised vector from retrieve.embed_query().
    Returns the best match regardless of threshold - the caller decides what
    counts as a hit."""
    ref_vecs, examples = _reference_vectors()
    sims = ref_vecs @ query_vec.reshape(-1)
    best = int(sims.argmax())
    return {
        "similarity": float(sims[best]),
        "nearest_example": examples[best],
        "threshold": float(ROUTE["legal_sensitive_similarity_threshold"]),
    }


def is_topic_match(query_vec: np.ndarray) -> dict:
    """Adds the pass/fail verdict against the configured threshold."""
    result = nearest_match(query_vec)
    result["matched"] = result["similarity"] >= result["threshold"]
    return result
