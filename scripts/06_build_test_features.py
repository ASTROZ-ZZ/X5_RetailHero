#!/usr/bin/env python3
"""Apply the frozen purchase-history definitions to official test customers."""

import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
from runpy import run_path
import sqlite3
from tempfile import TemporaryDirectory

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/06_offline_delivery"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT)
    out = parser.parse_args().output
    (out / "tables").mkdir(parents=True, exist_ok=True)
    (out / "metadata").mkdir(exist_ok=True)
    helpers = run_path(str(ROOT / "scripts/02_customer_analysis.py"))
    require = helpers["require"]
    stage02 = ROOT / "results/02_customer_analysis"
    definitions = json.loads((stage02 / "metadata/analysis_summary.json").read_text())
    _, codes, products, audit, split_hash = helpers["read_inputs"]()
    require(split_hash == definitions["split_file_sha256"], "Fixed split differs from stage 02")
    require(all(audit[k] == definitions[k] for k in ("history_start", "history_end")), "History window differs")
    test_path = ROOT / "data/uplift_test.csv"
    source = pd.read_csv(test_path, dtype=str)
    require(list(source.columns) == ["client_id"] and source.client_id.notna().all() and source.client_id.is_unique,
            "Invalid official test IDs")
    ids = pd.Index(source.client_id.sort_values())
    require(len(ids) > 0, "No official test customers")

    with TemporaryDirectory(prefix=".official-test-", dir=out) as work, closing(
        sqlite3.connect(Path(work) / "orders.sqlite")
    ) as db:
        lines, quantities, stats = helpers["build_orders"](
            db, ids, codes, products, 500_000, audit["history_start"], audit["history_end"]
        )
        expected = next(f["rows"] for f in audit["files"] if f["table"] == "purchases")
        require(stats["rows_scanned"] == expected, "Purchase row count differs from audit")
        customers, _, applied = helpers["summarize_customers"](
            db, ids, pd.Timestamp(definitions["reference_date"]), definitions["thresholds"]
        )
        helpers["category_results"](customers, codes, lines, quantities)
        require(int(customers.frequency.sum()) == stats["training_orders"], "Order counts do not reconcile")
        require(int(customers.monetary_cents.sum()) == stats["training_purchase_cents"], "Spending does not reconcile")
        features = customers.reset_index().drop(columns="monetary_cents")
        columns = pd.read_csv(stage02 / "tables/customer_features.csv", nrows=0).columns
        require(set(features) == set(columns), "Official test feature columns differ from training")
        staged = Path(work) / "official_test_features.csv"
        helpers["save"](features[columns], staged)
        fingerprint = hashlib.sha256(staged.read_bytes()).hexdigest()
        staged.replace(out / "tables" / staged.name)
    metadata = dict(
        status="PASS", customers=len(ids), rows_scanned=stats["rows_scanned"],
        purchase_lines=stats["training_purchase_lines"], orders=stats["training_orders"],
        history_start=audit["history_start"], history_end=audit["history_end"],
        reference_date=definitions["reference_date"], thresholds=applied, split_sha256=split_hash,
        official_test_sha256=hashlib.sha256(test_path.read_bytes()).hexdigest(), features_sha256=fingerprint,
    )
    payload = json.dumps(metadata, indent=2)
    (out / "metadata/official_test_features.json").write_text(payload + "\n")
    print(payload, flush=True)


if __name__ == "__main__":
    main()
