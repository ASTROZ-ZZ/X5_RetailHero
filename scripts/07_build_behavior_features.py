#!/usr/bin/env python3
"""Build purchase-rhythm features for train and validation customers only."""

import argparse
from pathlib import Path
import hashlib
import json

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/07_uplift_optimization"
STAGE02 = ROOT / "results/02_customer_analysis"
STAGE04 = ROOT / "results/04_uplift_baselines"
KEY = ["client_id", "transaction_id"]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT)
    out = parser.parse_args().output
    (out / "tables").mkdir(parents=True, exist_ok=True)
    (out / "metadata").mkdir(exist_ok=True)
    split_path = ROOT / "results/01_data_audit/splits/split_assignments.csv"
    split = pd.read_csv(split_path, dtype=str).set_index("client_id", verify_integrity=True).split
    split_hash = hashlib.sha256(split_path.read_bytes()).hexdigest()
    definitions = json.loads((STAGE02 / "metadata/analysis_summary.json").read_text())
    validation = json.loads((STAGE04 / "metadata/validation_features.json").read_text())
    require(split_hash == definitions["split_file_sha256"] == validation["split_sha256"],
            "Fixed split fingerprint differs")
    require(definitions["reference_date"] == validation["reference_date"], "Reference date differs")
    feature_fields = ["client_id", "frequency", "recency_days", "median_repurchase_gap_days"]
    blocks = []
    for name, path in [("train", STAGE02 / "tables/customer_features.csv"),
                       ("validation", STAGE04 / "tables/validation_features.csv")]:
        frame = pd.read_csv(path, dtype={"client_id": str}, usecols=feature_fields)
        require(frame.client_id.is_unique and set(frame.client_id) == set(split[split.eq(name)].index),
                f"Population differs: {name}")
        blocks.append(frame)
    features = pd.concat(blocks).set_index("client_id", verify_integrity=True).sort_index()
    ids = set(features.index)
    ref = pd.Timestamp(definitions["reference_date"])
    lower, middle, upper = ((ref - pd.Timedelta(days=d)).strftime("%Y-%m-%d") for d in (28, 14, 0))
    date = "transaction_datetime"
    pieces = []
    scanned = 0
    for i, chunk in enumerate(pd.read_csv(ROOT / "data/purchases.csv", usecols=[*KEY, date],
                                         dtype=str, chunksize=500_000), start=1):
        scanned += len(chunk)
        subset = chunk.loc[(chunk[date] >= lower) & (chunk[date] < upper) & chunk.client_id.isin(ids)]
        if len(subset):
            require(subset.notna().all().all(), "Incomplete recent order record")
            pieces.append(subset.drop_duplicates())
        if i == 1 or i % 20 == 0:
            print(f"Scanned {scanned:,} purchase rows", flush=True)
    require(bool(pieces), "No recent purchase records")
    orders = pd.concat(pieces, ignore_index=True).drop_duplicates()
    require(not orders.duplicated(KEY).any(), "Conflicting timestamps for a recent order")
    orders["recent"] = orders[date] >= middle
    counts = orders.groupby(["client_id", "recent"]).size().unstack(fill_value=0).reindex(
        index=features.index, columns=[False, True], fill_value=0
    )
    require(scanned == definitions["rows_scanned"], "Purchase row count differs from stage 02")
    require((counts.sum(axis=1) <= features.frequency).all(), "28-day counts exceed historical order counts")
    output = pd.DataFrame({
        "orders_previous_14d": counts[False], "orders_recent_14d": counts[True],
        "order_change_14d": counts[True] - counts[False],
        "recency_to_gap": features.recency_days.div(
            features.median_repurchase_gap_days.where(features.median_repurchase_gap_days > 0)
        ),
    })
    require(np.isfinite(output.recency_to_gap.dropna()).all(), "Invalid recency-to-gap ratio")
    path = out / "tables/behavior_features.csv"
    output.to_csv(path, encoding="utf-8-sig")
    meta = dict(
        status="PASS", development_customers=len(output), rows_scanned=scanned, distinct_orders_28d=len(orders),
        previous_interval=[lower, middle], recent_interval=[middle, upper], interval_end_exclusive=True,
        missing_recency_to_gap=int(output.recency_to_gap.isna().sum()),
        split_sha256=split_hash, behavior_features_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )
    payload = json.dumps(meta, indent=2)
    (out / "metadata/behavior_features.json").write_text(payload + "\n")
    print(payload, flush=True)


if __name__ == "__main__":
    main()
