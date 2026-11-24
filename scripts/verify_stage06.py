#!/usr/bin/env python3
"""Independently validate the X5 offline prediction delivery."""

import argparse
from collections import Counter
import csv
import hashlib
import json
from math import isfinite
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/06_offline_delivery"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def rows(path, header=None):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if header is not None:
            require(reader.fieldnames == header, f"Unexpected columns: {path.name}")
        yield from reader


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT)
    out = parser.parse_args().output
    meta = json.loads((out / "metadata/submission_summary.json").read_text())
    feature = json.loads((out / "metadata/official_test_features.json").read_text())
    test_ids = [r["client_id"] for r in rows(ROOT / "data/uplift_test.csv", ["client_id"])]
    ordered = [r["client_id"] for r in rows(ROOT / "data/uplift_sample_submission.csv", ["client_id", "uplift"])]
    path = out / "tables/uplift_submission.csv"
    ids, scores = [], []
    for row in rows(path, ["client_id", "uplift"]):
        require(None not in row and bool(row["client_id"]), "Malformed submission row")
        score = float(row["uplift"])
        require(isfinite(score) and -1 <= score <= 1, "Non-finite or out-of-range score")
        ids.append(row["client_id"])
        scores.append(score)
    require(ids == ordered, "Submission does not follow template ID order")
    require(len(ids) == len(set(ids)) == len(test_ids) == meta["scored_customers"] and set(ids) == set(test_ids),
            "Submission does not cover official customers exactly once")
    require([min(scores), max(scores)] == meta["score_range"] and len(set(scores)) > 1,
            "Score range differs or scores are constant")

    feature_path = out / "tables/official_test_features.csv"
    feature_ids, orders = [], 0
    for row in rows(feature_path):
        feature_ids.append(row["client_id"])
        orders += int(row["frequency"])
    require(len(feature_ids) == len(ids) and set(feature_ids) == set(ids) and orders == feature["orders"],
            "Official test feature IDs or order count differ")
    labeled = list(rows(ROOT / "data/uplift_train.csv", ["client_id", "treatment_flg", "target"]))
    labeled_ids = {r["client_id"] for r in labeled}
    require(labeled_ids.isdisjoint(ids) and len(labeled_ids) == len(labeled) == meta["labeled_customers"],
            "Labeled sample size differs or overlaps official test")
    counts = Counter(r["treatment_flg"] for r in labeled)
    require(counts == {"0": meta["labeled_control"], "1": meta["labeled_sms"]}, "Training arm size differs")
    require(hashlib.sha256(feature_path.read_bytes()).hexdigest() == feature["features_sha256"],
            "Official features fingerprint differs")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    require(digest == meta["prediction_sha256"], "Submission fingerprint differs")
    result = dict(
        status="PASS", scored_customers=len(ids), associated_history_orders=orders,
        labeled_customers=len(labeled), unique_scores=len(set(scores)), sha256=digest,
        checks=["exact_submission_columns", "exact_official_id_coverage", "unique_ids", "template_order",
                "finite_and_bounded_scores", "feature_coverage_and_order_count", "labeled_total_and_arm_counts",
                "official_test_disjoint_from_labeled", "feature_and_submission_fingerprints"],
    )
    payload = json.dumps(result, indent=2)
    (out / "metadata/verification.json").write_text(payload + "\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
