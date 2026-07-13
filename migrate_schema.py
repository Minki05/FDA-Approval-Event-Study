"""
migrate_schema.py  (v1.1 -> v1.2)

Purpose: make events_verified.csv CRL-ready without touching how
returns are computed. This is a pure schema/labeling step.

Changes:
  1. Standardize decision_type values to uppercase enums
     ("Approval" -> "APPROVAL"; CRL rows will use "CRL").
  2. Add an event_direction column as a *dictionary label* for the
     event type, NOT a prediction of price direction.
        APPROVAL -> POSITIVE
        CRL      -> NEGATIVE
     IMPORTANT: this is the ex-ante label of the event category only.
     A CRL is not guaranteed to move the stock down (the market may
     have already priced it in, or the CRL reason may be minor).
     Actual direction is always read off the abnormal-return sign,
     never assumed from this column.

Idempotent: running it twice is safe (already-migrated rows are
left as-is).
"""

import sys
import pandas as pd

INPUT = "events_verified.csv"
OUTPUT = "events_verified.csv"  # in-place; a .bak is written first

# canonical event-type enums
DECISION_TYPE_MAP = {
    "approval": "APPROVAL",
    "crl": "CRL",
    "complete response letter": "CRL",
}

DIRECTION_LABEL = {
    "APPROVAL": "POSITIVE",
    "CRL": "NEGATIVE",
}


def standardize_decision_type(value):
    key = str(value).strip().lower()
    return DECISION_TYPE_MAP.get(key, str(value).strip().upper())


def main():
    df = pd.read_csv(INPUT)
    print(f"Loaded {len(df)} rows from {INPUT}")

    if "decision_type" not in df.columns:
        print("ERROR: no decision_type column found", file=sys.stderr)
        sys.exit(1)

    # backup before writing
    df.to_csv(INPUT + ".bak", index=False)
    print(f"Backup written to {INPUT}.bak")

    # 1. standardize decision_type
    before = df["decision_type"].value_counts().to_dict()
    df["decision_type"] = df["decision_type"].apply(standardize_decision_type)
    after = df["decision_type"].value_counts().to_dict()
    print(f"decision_type: {before} -> {after}")

    # 2. add / refresh event_direction as an event-type label
    unknown = set(df["decision_type"]) - set(DIRECTION_LABEL)
    if unknown:
        print(f"WARNING: decision_type values with no direction label: {unknown}")
    df["event_direction"] = df["decision_type"].map(DIRECTION_LABEL).fillna("UNKNOWN")
    print(f"event_direction: {df['event_direction'].value_counts().to_dict()}")

    # place event_direction right after decision_type for readability
    cols = list(df.columns)
    cols.remove("event_direction")
    insert_at = cols.index("decision_type") + 1
    cols.insert(insert_at, "event_direction")
    df = df[cols]

    df.to_csv(OUTPUT, index=False)
    print(f"Wrote {len(df)} rows to {OUTPUT}")
    print(f"Columns now: {list(df.columns)}")


if __name__ == "__main__":
    main()
