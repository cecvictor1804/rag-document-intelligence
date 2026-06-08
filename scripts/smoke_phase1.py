"""Phase 1 smoke check: import every module and run the loaders + chunker over
the real sample docs. No DB or network required. Run:

    PYTHONPATH=backend:. python scripts/smoke_phase1.py
"""

from __future__ import annotations

import importlib
from pathlib import Path

MODULES = [
    "app.config",
    "app.logging",
    "app.core.models",
    "app.core.interfaces",
    "app.core.resilience",
    "app.db.pool",
    "app.db.migrate",
    "app.embeddings",
    "app.embeddings.voyage",
    "app.embeddings.openai",
    "app.vectorstore",
    "app.vectorstore.pgvector",
    "ingestion.pipeline.hashing",
    "ingestion.pipeline.clean",
    "ingestion.pipeline.chunk",
    "ingestion.pipeline.loaders",
    "ingestion.pipeline.source",
    "ingestion.pipeline.indexer",
    "ingestion.pipeline.run",
    "ingestion.pipeline.worker",
]


def main() -> None:
    for m in MODULES:
        importlib.import_module(m)
    print(f"OK: imported {len(MODULES)} modules cleanly")

    from ingestion.pipeline.chunk import chunk_text
    from ingestion.pipeline.clean import clean_text
    from ingestion.pipeline.loaders import load_document

    root = Path(__file__).resolve().parent.parent / "sample_docs"
    for p in sorted(root.iterdir()):
        if not p.is_file():
            continue
        title, text = load_document(p.read_bytes(), p.name)
        chunks = chunk_text(clean_text(text), chunk_tokens=600, overlap_tokens=90)
        sections = sorted({c.section for c in chunks if c.section})
        print(f"  {p.name}: title={title!r} chunks={len(chunks)} sections={sections}")


if __name__ == "__main__":
    main()
