"""
Regenerate the inventory section of FOLDER-DESCRIPTION.md.

A folder map that has to be hand-maintained goes stale, and a stale map is worse
than no map because it gets trusted. So the mechanical part - the tree, file
sizes, git state, index statistics - is generated, while the hand-written
explanation of *what each thing is for* is preserved untouched.

The split is marked in the file by:

    <!-- BEGIN GENERATED INVENTORY -->
    ...everything here is overwritten...
    <!-- END GENERATED INVENTORY -->

Everything outside those markers is yours to write. Run from anywhere:

    python .claude/skills/pm4-project-context/scripts/refresh_folder_description.py
"""
from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path

# scripts/ -> pm4-project-context/ -> skills/ -> .claude/ -> project root
ROOT = Path(__file__).resolve().parents[4]
TARGET = (
    ROOT / ".claude" / "skills" / "pm4-project-context" / "references" / "FOLDER-DESCRIPTION.md"
)

BEGIN = "<!-- BEGIN GENERATED INVENTORY -->"
END = "<!-- END GENERATED INVENTORY -->"


def git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return ""


def human(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def tracked_files() -> list[tuple[str, int]]:
    listing = git("ls-files")
    rows: list[tuple[str, int]] = []
    for rel in listing.splitlines():
        path = ROOT / rel
        rows.append((rel, path.stat().st_size if path.exists() else 0))
    return sorted(rows)


def untracked_data() -> dict[str, list[str]]:
    """Directories deliberately kept out of git - worth listing so their absence
    from the repo is not mistaken for their absence on disk."""
    out: dict[str, list[str]] = {}
    for rel in ("data/raw", "data/logs", "eval/results"):
        directory = ROOT / rel
        out[rel] = sorted(p.name for p in directory.iterdir()) if directory.is_dir() else []
    return out


def index_stats() -> dict | None:
    meta = ROOT / "data" / "index" / "meta.json"
    if not meta.exists():
        return None
    try:
        return json.loads(meta.read_text(encoding="utf-8"))
    except Exception:
        return None


def build_inventory() -> str:
    lines: list[str] = [BEGIN, ""]
    lines.append(f"*Generated {date.today().isoformat()} by `refresh_folder_description.py`.*")
    lines.append("")

    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    head = git("log", "-1", "--pretty=format:%h %s")
    remote = git("config", "--get", "remote.origin.url")
    dirty = git("status", "--porcelain")

    lines.append("## Repository state")
    lines.append("")
    lines.append(f"- Branch: `{branch or 'n/a'}`")
    lines.append(f"- HEAD: `{head or 'n/a'}`")
    lines.append(f"- Remote: {remote or 'n/a'}")
    lines.append(f"- Working tree: {'has uncommitted changes' if dirty else 'clean'}")
    lines.append("")

    stats = index_stats()
    if stats:
        lines.append("## Built index")
        lines.append("")
        lines.append(
            f"- {stats.get('document_count', '?')} documents, "
            f"{stats.get('chunk_count', '?')} chunks"
        )
        lines.append(f"- Doc types: {', '.join(stats.get('doc_types_indexed', []))}")
        lines.append(
            f"- Embeddings: `{stats.get('embedding_model', '?')}` "
            f"({stats.get('dimension', '?')}d)"
        )
        lines.append("")

    lines.append("## Tracked files")
    lines.append("")
    lines.append("| Path | Size |")
    lines.append("|---|---|")
    for rel, size in tracked_files():
        lines.append(f"| `{rel}` | {human(size)} |")
    lines.append("")

    lines.append("## Present on disk but not committed")
    lines.append("")
    lines.append(
        "Deliberate - see `decisions.md`. Regenerable, runtime, or per-run output."
    )
    lines.append("")
    for rel, names in untracked_data().items():
        shown = ", ".join(f"`{n}`" for n in names) if names else "*(empty)*"
        lines.append(f"- **`{rel}/`** — {shown}")
    lines.append("")
    lines.append(END)
    return "\n".join(lines)


def main() -> None:
    inventory = build_inventory()

    if TARGET.exists():
        text = TARGET.read_text(encoding="utf-8")
        if BEGIN in text and END in text:
            head = text.split(BEGIN)[0]
            tail = text.split(END)[1]
            TARGET.write_text(head + inventory + tail, encoding="utf-8", newline="\n")
            print(f"Refreshed inventory in {TARGET.relative_to(ROOT)} (prose preserved).")
            return
        # Markers missing - append rather than clobber whatever is there.
        TARGET.write_text(text.rstrip() + "\n\n" + inventory + "\n", encoding="utf-8", newline="\n")
        print(f"Markers not found; appended inventory to {TARGET.relative_to(ROOT)}.")
        return

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(inventory + "\n", encoding="utf-8", newline="\n")
    print(f"Created {TARGET.relative_to(ROOT)}.")


if __name__ == "__main__":
    main()
