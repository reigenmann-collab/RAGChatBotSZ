"""
REQ-08 / REQ-09 - Pseudonymised audit logging.

REQ-08 requires that personally identifiable information in monitoring logs is
anonymised or pseudonymised. REQ-09 requires that all escalations and caseworker
reviews are logged for auditability. Those two pull in opposite directions, so
the split here is explicit:

  - The raw query text is NEVER written while pseudonymise is true. What is
    written is a salted SHA-256 digest, which lets an auditor confirm that two
    entries came from the same question without recovering the question.
  - Everything needed to audit a routing decision - the signals, the threshold,
    the decision, the documents used - is written in full, because none of it is
    personal data.

The salt belongs in the environment (PM4_LOG_SALT), not in the repository. An
unsalted hash of a short free-text query is trivially reversible by dictionary
attack, which would defeat the pseudonymisation entirely.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import load_config, log_salt, path  # noqa: E402

CFG = load_config()
LOG = CFG["logging"]


def query_pseudonym(query: str) -> str:
    digest = hashlib.sha256((log_salt() + "|" + query.strip().lower()).encode("utf-8"))
    return "q_" + digest.hexdigest()[:16]


def write(record: dict) -> None:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "query_pseudonym": query_pseudonym(record.get("query", "")),
        "decision": record.get("decision"),
        "escalated": record.get("escalate"),
        "reason": record.get("reason"),
        "threshold": record.get("threshold"),
        "signals": record.get("signals"),
        "coverage": record.get("coverage"),
        "retrieved": record.get("retrieved_chunk_ids"),
        "retrieved_doc_types": record.get("retrieved_doc_types"),
        "latency_seconds": record.get("latency_seconds"),
        "model": record.get("model"),
    }

    if not LOG.get("pseudonymise", True):
        entry["query"] = record.get("query")

    with open(path(*LOG["path"].split("/")), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_all() -> list[dict]:
    log_file = path(*LOG["path"].split("/"))
    if not log_file.exists():
        return []
    with open(log_file, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]
