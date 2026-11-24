#!/usr/bin/env python3
"""Apply the existing customer feature definitions to a reserved split."""

import argparse
from contextlib import closing
import json
from pathlib import Path
from runpy import run_path
import sqlite3
from tempfile import TemporaryDirectory

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/04_uplift_baselines"
HOLDOUT_OUT = ROOT / "results/05_holdout_evaluation"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("validation", "holdout"), default="validation")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    out = args.output or (OUT if args.split == "validation" else HOLDOUT_OUT)
    filename = f"{args.split}_features"
    (out / "tables").mkdir(parents=True, exist_ok=True)
    (out / "metadata").mkdir(exist_ok=True)
    stage02 = ROOT / "results/02_customer_analysis"
    summary = json.loads((stage02 / "metadata/analysis_summary.json").read_text())
    helpers = run_path(str(ROOT / "scripts/02_customer_analysis.py"))
    ids, codes, products, audit, split_hash = helpers["read_inputs"](args.split)
    require = helpers["require"]
    require(split_hash == summary["split_file_sha256"], "Split file differs from stage 02")
    require(all(audit[k] == summary[k] for k in ("history_start", "history_end")), "History window differs")
    with TemporaryDirectory(prefix=f".{args.split}-", dir=out) as work, closing(
        sqlite3.connect(Path(work) / "orders.sqlite")
    ) as db:
        lines, quantities, stats = helpers["build_orders"](
            db, ids, codes, products, 500_000, audit["history_start"], audit["history_end"]
        )
        expected = next(f["rows"] for f in audit["files"] if f["table"] == "purchases")
        require(stats["rows_scanned"] == expected, "Purchase row count differs from audit")
        customers, _, applied = helpers["summarize_customers"](
            db, ids, pd.Timestamp(summary["reference_date"]), summary["thresholds"]
        )
        helpers["category_results"](customers, codes, lines, quantities)
        require(int(customers.frequency.sum()) == stats["training_orders"], "Order counts do not reconcile")
        require(int(customers.monetary_cents.sum()) == stats["training_purchase_cents"], "Spending does not reconcile")
        features = customers.reset_index().drop(columns="monetary_cents")
        columns = pd.read_csv(stage02 / "tables/customer_features.csv", nrows=0).columns
        require(set(features) == set(columns), f"{args.split} feature columns differ from training")
        temp_file = Path(work) / f"{filename}.csv"
        helpers["save"](features[columns], temp_file)
        temp_file.replace(out / "tables" / f"{filename}.csv")
        metadata = dict(
            status="PASS", split=args.split, customers=len(ids), rows_scanned=stats["rows_scanned"],
            purchase_lines=stats["training_purchase_lines"], orders=stats["training_orders"],
            reference_date=summary["reference_date"], thresholds=applied, split_sha256=split_hash,
        )
        (out / "metadata" / f"{filename}.json").write_text(json.dumps(metadata, indent=2) + "\n")
        print(json.dumps(metadata, indent=2), flush=True)


if __name__ == "__main__":
    main()
