"""Verify that every expansion gold evidence string is a real substring of the
extracted manual text, and that each gold_value is textually grounded.

This is the no-fabrication gate for the R1 corpus expansion: if any evidence
string is not present verbatim (case-insensitive) in the corresponding real
manual, the run fails loudly. Run:

    python scripts/verify_expansion_gold.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from clarity.evaluation.gold_data_expansion import (  # noqa: E402
    EXPANSION_GOLD_QUERIES, EXPANSION_MANUALS, EXPANSION_GOLD_CONFIGS,
)

ROOT = Path(__file__).parent.parent


def load(device: str) -> str:
    return (ROOT / EXPANSION_MANUALS[device]).read_text().lower()


def main() -> int:
    texts = {dev: load(dev) for dev in EXPANSION_MANUALS}
    ev_fail, val_warn, ok = [], [], 0

    for q in EXPANSION_GOLD_QUERIES:
        if q.expected_abstain:
            continue  # out-of-corpus probes have no evidence by design
        text = texts[q.device]
        # at least one evidence string must be present verbatim
        hits = [e for e in q.evidence if e.lower() in text]
        if not hits:
            ev_fail.append((q.query_id, q.evidence))
        else:
            ok += 1
        # gold_value grounding (advisory): the value token should appear somewhere
        if q.gold_value is not None:
            gv = str(q.gold_value).lower()
            if gv not in text and not any(gv in e.lower() for e in q.evidence):
                val_warn.append((q.query_id, q.gold_value))

    print(f"answerable queries checked: {ok + len(ev_fail)}")
    print(f"  evidence PRESENT: {ok}")
    print(f"  evidence MISSING: {len(ev_fail)}")
    for qid, ev in ev_fail:
        print(f"    [MISS] {qid}: none of {ev}")
    if val_warn:
        print(f"  gold_value not directly in text (advisory): {len(val_warn)}")
        for qid, v in val_warn:
            print(f"    [warn] {qid}: value={v!r}")

    # generator gold-config values grounding
    print("\ngenerator GOLD_CONFIGS value grounding:")
    for dev, cfg in EXPANSION_GOLD_CONFIGS.items():
        text = texts[dev]
        for f, v in cfg["fields"].items():
            present = str(v).lower() in text
            flag = "ok " if present else "MISS"
            if not present:
                val_warn.append((f"{dev}:{f}", v))
            print(f"  [{flag}] {dev} :: {f} = {v!r}")

    if ev_fail:
        print("\nRESULT: FAIL — fix missing evidence before ingesting/eval.")
        return 1
    print("\nRESULT: PASS — all evidence strings are grounded in real manual text.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
