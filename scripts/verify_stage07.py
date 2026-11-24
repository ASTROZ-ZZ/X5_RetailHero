#!/usr/bin/env python3
"""Recompute development-fold and behavioral-feature checks from saved data."""

import argparse
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import json
from math import isclose, isfinite
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/07_uplift_optimization"


def rows(path):
    reader = gzip.open if path.suffix == ".gz" else open
    with reader(path, "rt", newline="", encoding="utf-8-sig") as handle:
        yield from csv.DictReader(handle)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT)
    out = parser.parse_args().output
    plan = json.loads((out / "metadata/cv_plan.json").read_text())
    feature_meta = json.loads((out / "metadata/behavior_features.json").read_text())
    stage02 = ROOT / "results/02_customer_analysis/tables"
    train_counts = Counter()
    previous, recent, end = [*feature_meta["previous_interval"], feature_meta["recent_interval"][1]]
    for r in rows(stage02 / "training_orders.csv.gz"):
        date = r["transaction_datetime"][:10]
        if previous <= date < end:
            train_counts[r["client_id"], date >= recent] += 1
    train = {r["client_id"] for r in rows(stage02 / "customer_features.csv")}
    split_path = ROOT / "results/01_data_audit/splits/split_assignments.csv"
    population = {r["client_id"] for r in rows(split_path) if r["split"] in plan["population"]}
    seen, orders = set(), 0
    for r in rows(out / "tables/behavior_features.csv"):
        cid = r["client_id"]
        a, b = int(r["orders_previous_14d"]), int(r["orders_recent_14d"])
        require(cid not in seen and b-a == int(r["order_change_14d"]), "Invalid feature row")
        if cid in train:
            require((a, b) == (train_counts[cid, False], train_counts[cid, True]),
                    "14-day counts differ from training order export")
        seen.add(cid)
        orders += a+b
    require(seen == population and orders == feature_meta["distinct_orders_28d"], "Feature coverage or order count differs")
    labels = {r["client_id"]: (int(r["treatment_flg"]), int(r["target"]))
              for r in rows(ROOT / "data/uplift_train.csv") if r["client_id"] in population}
    require(set(labels) == population, "Development outcomes do not cover population")

    scores = defaultdict(list)
    repeats = defaultdict(set)
    for r in rows(out / "tables/fold_scores.csv.gz"):
        repeat, fold, cid = int(r["repeat"]), int(r["fold"]), r["client_id"]
        require(cid in population and cid not in repeats[repeat], "Duplicate or out-of-scope fold score")
        require(all(isfinite(float(r[k])) for k in plan["variants"]), "Invalid prediction")
        repeats[repeat].add(cid)
        scores[repeat, fold].append(r)
    require(len(repeats) == len(plan["repeat_seeds"]) and all(v == population for v in repeats.values()),
            "Out-of-fold scores do not cover the population once per repetition")

    def recompute(block, ranking, r):
        k = len(block) * plan["reach_pct"] // 100
        counts = Counter(labels[record["client_id"]] for record in sorted(block, key=ranking)[:k])
        n0, n1 = [counts[a, 0] + counts[a, 1] for a in (0, 1)]
        require((n0, n1, counts[0, 1], counts[1, 1], k) == tuple(int(r[field]) for field in
                ("control_n", "sms_n", "control_buyers", "sms_buyers", "selected")), "Ranked counts differ")
        actual = 100 * (counts[1, 1]/n1 - counts[0, 1]/n0)
        require(isclose(actual, float(r["uplift_pp"]), abs_tol=1e-12), "Fold uplift differs")
        return actual

    random = defaultdict(list)
    for r in rows(out / "tables/random_fold_metrics.csv"):
        key = int(r["repeat"]), int(r["fold"])
        seed = int(r["random_seed"])
        def key_random(item):
            cid = item["client_id"]
            return hashlib.sha256(f"{seed}:{cid}".encode()).digest()[:8], cid
        random[key].append(recompute(scores[key], key_random, r))
    require(set(random) == set(scores) and all(len(v) == len(plan["random_seeds"]) for v in random.values()),
            "Random reference coverage differs")
    lifts = defaultdict(list)
    for r in rows(out / "tables/fold_metrics.csv"):
        key = int(r["repeat"]), int(r["fold"])
        model = r["model"]
        score = recompute(scores[key], lambda item: (-float(item[model]), item["client_id"]), r)
        delta = score - mean(random[key])
        require(isclose(delta, float(r["vs_random_pp"]), abs_tol=1e-12), "Fold difference differs")
        lifts[model].append(delta)
    summary = {r["model"]: r for r in rows(out / "tables/model_summary.csv")}
    require(set(lifts) == set(summary) == set(plan["variants"]), "Model coverage differs")
    for model, values in lifts.items():
        require(len(values) == len(scores) and isclose(mean(values), float(summary[model]["mean_vs_random_pp"]),
                                                       abs_tol=1e-12), "Model summary differs")
    metadata = json.loads((out / "metadata/cv_summary.json").read_text())
    require(metadata["best_by_mean_vs_random"] == max(lifts, key=lambda k: mean(lifts[k])), "Candidate differs")
    result = dict(status="PASS", development_customers=len(population), checked_folds=len(scores),
                  model_fold_metrics=sum(map(len, lifts.values())), random_fold_metrics=sum(map(len, random.values())),
                  checks=["training_window_counts_against_order_export", "development_only_feature_and_label_coverage",
                          "exactly_one_out_of_fold_score_per_customer_per_repeat", "model_and_random_top30_counts",
                          "fold_uplift_and_mean_candidate"])
    payload = json.dumps(result, indent=2)
    (out / "metadata/verification.json").write_text(payload + "\n")
    print(payload)


if __name__ == "__main__":
    main()
