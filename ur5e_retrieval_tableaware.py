"""R1.2: UR5e full retrieval (dense/sparse/hybrid/rerank) with vs without
table-aware chunking, WITHOUT the generation/deployment step (no bridge/Ollama).

Reuses the case-study harness functions. Writes one JSON per chunking mode.
    python scripts/ur5e_retrieval_tableaware.py --table-aware --out <path>
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from clarity.config import DEFAULT_CONFIG
from clarity.evaluation.ur5e_case_study import (
    build_corpus, label_relevance, evaluate_retrieval_full,
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--table-aware", action="store_true")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    chunks, corpus_stats = build_corpus(table_aware=args.table_aware)
    labels = label_relevance(chunks)
    retrieval, _, _ = evaluate_retrieval_full(chunks, labels, DEFAULT_CONFIG)

    out = {"table_aware": args.table_aware, "corpus": corpus_stats, "retrieval": retrieval}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2))

    print(f"table_aware={args.table_aware}")
    for name in ["dense", "sparse", "hybrid", "rerank"]:
        m = retrieval.get(name) or retrieval.get("metrics", {}).get(name, {})
        if m:
            print(f"  {name:8s} HR@10={m.get('HitRate@10', 0):.3f} MRR@10={m.get('MRR@10', 0):.3f}")


if __name__ == "__main__":
    main()
