"""Seed the three grounding stores from the banking domain pack.

Acceptance criterion 3: prints document, chunk, node and relationship counts
that must match what the grounding panel shows. The counts are read back from
the stores after writing rather than echoed from the fixture, because a count
that cannot disagree with reality proves nothing.

    python backend/scripts/seed_data.py [--reset] [--no-vector] [--if-empty]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import records as record_store  # noqa: E402
from app.db.models import migrate  # noqa: E402
from app.graph import extract  # noqa: E402
from app.graph.base import active_backend, close_store, get_store, select_backend  # noqa: E402
from app.logging_setup import configure_logging  # noqa: E402
from app.rag import ingest, store as vector_store  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the grounding stores")
    parser.add_argument("--reset", action="store_true",
                        help="clear the vector, graph and relational stores first")
    parser.add_argument("--no-vector", action="store_true",
                        help="skip embedding (graph and relational only)")
    parser.add_argument("--if-empty", action="store_true",
                        help="no-op when the stores already hold data (startup use)")
    args = parser.parse_args()

    configure_logging()
    migrate()
    select_backend()
    try:
        graph = get_store()
    except RuntimeError as exc:
        # Kuzu is a single-writer embedded store: a running backend holds the
        # lock. Say so, rather than leaking a stack trace about a lock file.
        if "lock" in str(exc).lower():
            print("ERROR: the graph store is locked by another process.")
            print("       Stop the backend and re-run, or use POST /api/grounding/reseed")
            print("       to re-seed in-process while it is running.")
            return 1
        raise

    print(f"graph backend      : {active_backend()}")

    if args.if_empty and graph.counts()["nodes"] and vector_store.stats()["chunks"]:
        print("stores already seeded; nothing to do")
        close_store()
        return 0

    if args.reset:
        graph.clear()
        record_store.clear()
        if not args.no_vector:
            vector_store.reset()
        print("stores cleared")

    fixture = extract.load_records()
    relational = record_store.load(fixture)

    result = ingest.IngestResult()
    if not args.no_vector:
        result = ingest.ingest_corpus(reset=args.reset)
        extract.extract_documents(result.documents, result.chunks)

    extract.extract_records(fixture)
    edges = extract.extract_policy_edges(fixture)

    counts = graph.counts()
    vstats = vector_store.stats() if not args.no_vector else {"chunks": 0, "documents": 0}

    print()
    print("--- vector (Chroma) ---")
    print(f"documents          : {vstats['documents']}")
    print(f"chunks             : {vstats['chunks']}")
    if not args.no_vector:
        embedder = vstats["embedder"]
        print(f"embedder           : {embedder['backend']} (dim {embedder['dimension']})")
        if embedder["degraded"]:
            print("WARNING            : degraded embedder - retrieval quality is reduced")
        for tier, count in sorted(vstats["by_tier"].items()):
            print(f"  {tier:<28} {count}")

    print()
    print("--- graph ---")
    print(f"nodes              : {counts['nodes']}")
    print(f"relationships      : {counts['relationships']}")
    for label, count in counts["by_label"].items():
        print(f"  {label:<28} {count}")
    for label, count in counts["by_relationship"].items():
        print(f"  :{label:<27} {count}")

    print()
    print("--- relational (SQLite) ---")
    for table, count in record_store.counts().items():
        print(f"  {table:<28} {count}")

    if result.skipped:
        print()
        print("--- skipped ---")
        for item in result.skipped:
            print(f"  {item['path']}: {item['reason']}")

    print()
    print(f"policy edges declared/written: {len(fixture.get('policy_edges', []))}/{edges}")
    print(f"transactions carrying a fraud flag: "
          f"{sum(1 for t in fixture['transactions'] if t['fraud_flag'])}")
    print(f"relational rows loaded: {sum(relational.values())}")
    close_store()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
