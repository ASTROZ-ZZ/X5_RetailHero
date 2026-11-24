#!/usr/bin/env python3
"""Independently reconcile the exported training orders and customer results."""

import argparse
from collections import Counter
import csv
from decimal import Decimal
import gzip
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def records(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        yield from csv.DictReader(handle)


def require(condition, description):
    if not condition:
        raise ValueError(description)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "results/02_customer_analysis")
    args = parser.parse_args()
    out = args.output
    metadata = out / "metadata"
    stats = json.loads((metadata / "analysis_summary.json").read_text(encoding="utf-8"))
    split = ROOT / "results/01_data_audit/splits/split_assignments.csv"
    require(hashlib.sha256(split.read_bytes()).hexdigest() == stats["split_file_sha256"], "Split fingerprint differs")
    train = {r["client_id"] for r in records(split) if r["split"] == "train"}

    cents, orders = Counter(), Counter()
    lines = 0
    previous = ("", "")
    with gzip.open(out / "tables/training_orders.csv.gz", "rt", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            key = row["client_id"], row["transaction_id"]
            require(previous < key, f"Duplicate or out-of-order order: {key}")
            previous = key
            client, _ = key
            orders[client] += 1
            cents[client] += int(row["purchase_sum"].replace(".", ""))
            lines += int(row["line_count"])

    customers = list(records(out / "tables/customer_features.csv"))
    require(len(customers) == len(train) == stats["training_customers"], "Customer row count differs")
    require({r["client_id"] for r in customers} == set(orders) == train, "Training population differs")
    segment_counts = Counter()
    for row in customers:
        cid = row["client_id"]
        require(int(row["frequency"]) == orders[cid] and Decimal(row["monetary"]) * 100 == cents[cid],
                f"Customer order or spending total differs: {cid}")
        require(bool(row["median_repurchase_gap_days"]) == (int(row["purchase_days"]) > 1),
                f"Unexpected repurchase availability: {cid}")
        segment_counts[row["segment"]] += 1
    for row in records(out / "tables/segment_summary.csv"):
        require(int(row["customers"]) == segment_counts[row["segment"]], "Segment count differs")

    require(sum(orders.values()) == stats["training_orders"], "Order total differs")
    require(sum(cents.values()) == stats["training_purchase_cents"], "Spending total differs")
    all_categories = [r for r in records(out / "tables/category_preferences.csv") if r["segment"] == "全部训练客户"]
    require(lines == stats["training_purchase_lines"] == sum(int(r["line_count"]) for r in all_categories),
            "Line and category totals differ")
    cohort_sizes = Counter(row["cohort_month"] for row in customers)
    for row in records(out / "tables/cohort_repeat.csv"):
        n = cohort_sizes[row["cohort_month"]]
        require(n == int(row["cohort_customers"]), "Cohort size differs")
        if row["status"] == "complete":
            active = int(float(row["active_customers_observed"]))
            require(0 <= active <= n and abs(float(row["repeat_rate"]) - active / n) < 1e-12,
                    "Cohort rate differs")
        else:
            require(not row["repeat_rate"], "Incomplete month has a reported rate")

    report = dict(
        status="PASS", training_customers=len(train), orders=sum(orders.values()), purchase_lines=lines,
        monetary_cents=sum(cents.values()), split_sha256=stats["split_file_sha256"],
        checks=["fixed_split_fingerprint", "unique_order_keys", "customer_order_and_spending_totals",
                "repurchase_availability", "segment_population", "category_line_reconciliation",
                "cohort_denominators_and_censoring"],
    )
    (metadata / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
