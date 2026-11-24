#!/usr/bin/env python3
"""Evaluate the validation-selected policy once at locked 30% reach."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
from runpy import run_path

import numpy as np
import pandas as pd
import sklearn


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/05_holdout_evaluation"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_labels(ids):
    with (ROOT / "data/uplift_train.csv").open(newline="", encoding="utf-8-sig") as handle:
        rows = [
            (r["client_id"], int(r["treatment_flg"]), int(r["target"]))
            for r in csv.DictReader(handle) if r["client_id"] in ids
        ]
    frame = pd.DataFrame(rows, columns=["client_id", "treatment_flg", "target"])
    if not (frame.client_id.is_unique and set(frame.client_id) == ids and
            frame[["treatment_flg", "target"]].isin([0, 1]).all().all()):
        raise ValueError("Experiment labels differ from the requested split")
    return frame


def score(out, lock, base):
    require = base["require"]
    features = ["client_id", *base["NUMERIC"], *base["CATEGORICAL"]]
    splits = pd.read_csv(ROOT / "results/01_data_audit/splits/split_assignments.csv", dtype=str)
    ids = {name: set(splits.loc[splits.split.eq(name), "client_id"])
           for name in ("train", "validation", "holdout")}
    stage04 = ROOT / "results/04_uplift_baselines"
    stage02 = ROOT / "results/02_customer_analysis"
    definitions = read_json(stage02 / "metadata/analysis_summary.json")
    extraction = read_json(out / "metadata/holdout_features.json")
    require(extraction["split"] == "holdout" and extraction["status"] == "PASS" and
            extraction["split_sha256"] == lock["model"]["split_sha256"],
            "Holdout feature metadata does not match lock")
    for key in ("reference_date", "thresholds"):
        require(extraction[key] == definitions[key], f"Holdout feature definition differs: {key}")
    paths = {
        "train": stage02 / "tables/customer_features.csv",
        "validation": stage04 / "tables/validation_features.csv",
        "holdout": out / "tables/holdout_features.csv",
    }
    frames = {}
    for key, path in paths.items():
        frame = pd.read_csv(path, dtype={"client_id": str}, usecols=features).sort_values("client_id")
        require(frame.client_id.is_unique and set(frame.client_id) == ids[key], f"Unexpected {key} features")
        frames[key] = frame
    train = frames["train"].merge(read_labels(ids["train"]), on="client_id", validate="one_to_one")
    require(len(train) == lock["model"]["training_customers"], "Unexpected training sample size")
    policies = [lock["candidate"], *lock["comparators"]]
    score_frames = pd.concat([frames["validation"], frames["holdout"]], ignore_index=True)
    predictions, encoded = base["predict"](train, score_frames, policies)
    require(encoded == lock["model"]["encoded_feature_count"], "Encoded feature count differs")
    split_index = len(frames["validation"])
    replay = pd.read_csv(stage04 / "tables/validation_scores.csv.gz",
                         dtype={"client_id": str, "random": str}, float_precision="round_trip")
    val_ids = frames["validation"].client_id.to_numpy()
    require(np.array_equal(val_ids, replay.client_id), "Validation replay ID order differs")
    errors = {}
    for name in policies:
        current, saved = predictions[name][:split_index], replay[name].to_numpy()
        if name == "random":
            require(np.array_equal(current, saved), "Random policy differs")
            errors[name] = 0.0
        else:
            errors[name] = float(np.max(np.abs(current - saved)))
            require(errors[name] < 1e-10, f"Validation score replay differs: {name}")
        k = split_index * lock["reach_pct"] // 100
        require(np.array_equal(base["rank"](val_ids, name, current)[:k],
                               base["rank"](val_ids, name, saved)[:k]),
                f"Validation top list differs: {name}")

    holdout_ids = frames["holdout"].client_id.to_numpy()
    holdout = pd.DataFrame({"client_id": holdout_ids})
    for name in policies:
        holdout[name] = predictions[name][split_index:]
        ordering = base["rank"](holdout_ids, name, holdout[name].to_numpy())
        ranks = np.empty(len(ordering), dtype=int)
        ranks[ordering] = np.arange(1, len(ordering) + 1)
        holdout[f"{name}_rank"] = ranks
    path = out / "tables/holdout_scores.csv.gz"
    holdout.to_csv(path, index=False, compression={"method": "gzip", "mtime": 0})
    return path, errors


def evaluate(path, lock, base):
    scores = pd.read_csv(path, dtype={"client_id": str, "random": str}, float_precision="round_trip")
    ids = set(scores.client_id)
    frame = scores.merge(read_labels(ids), on="client_id", validate="one_to_one")
    t, y = frame.treatment_flg.to_numpy(), frame.target.to_numpy()
    pct = lock["reach_pct"]
    require = base["require"]
    require(len(frame) * pct // 100 == lock["selected_count"], "Unexpected holdout reach count")
    rankings, details = {}, []
    for name in [lock["candidate"], *lock["comparators"]]:
        order = base["rank"](frame.client_id.to_numpy(), name, frame[name].to_numpy())
        require(np.array_equal(order, np.argsort(frame[f"{name}_rank"].to_numpy())), f"Rank differs: {name}")
        rankings[name] = order
        details.append(base["policy_curve"](name, order, t, y, percentages=[pct]))
    metrics = pd.concat(details, ignore_index=True).set_index("policy")
    comparisons = base["paired_at30"](lock["candidate"], rankings, t, y, metrics, lock["comparators"])
    return metrics, comparisons


def report(out, metrics, comparisons, lock, passed, names, customers):
    label = names[lock["candidate"]]
    best = metrics.loc[lock["candidate"]]
    conclusion = (
        "按预先锁定的规则，候选同时优于随机和 RFM，可作为下一阶段官方测试打分的首选策略。"
        if passed else
        "按预先锁定的规则，目前证据不足以确认候选同时优于两条基线。"
        "保留该次评估结果，后续模型修改需要独立样本再次验证。"
    )
    text = [
        "# X5 最终保留集评估", "",
        f"在固定的 {customers:,} 位保留客户上，每种策略选择前 {lock['selected_count']:,} 人。"
        f"锁定的 {label} 得到 **{best.uplift_pp:+.2f} 个百分点**"
        f"（95% CI [{best.ci_low_pp:+.2f}, {best.ci_high_pp:+.2f}]）。{conclusion}", "",
        "| 策略 | 短信组人数 | 对照组人数 | 短信组购买率 | 对照组购买率 | Uplift@30% | 95% CI（百分点） |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for name, r in metrics.iterrows():
        text.append(f"| {names[name]} | {int(r.sms_n):,} | {int(r.control_n):,} | {r.sms_rate:.2%} | "
                    f"{r.control_rate:.2%} | {r.uplift_pp:+.2f} | [{r.ci_low_pp:+.2f}, {r.ci_high_pp:+.2f}] |")
    text += ["", "## 相同触达比例下的直接对比", "",
             "| 对照策略 | 候选领先（百分点） | 配对 95% CI（百分点） | 名单重叠 |",
             "|---|---:|---|---:|"]
    for r in comparisons.itertuples():
        text.append(f"| {names[r.comparator]} | {r.difference_pp:+.2f} | "
                    f"[{r.ci_low_pp:+.2f}, {r.ci_high_pp:+.2f}] | {r.overlap_pct:.1f}% |")
    text += [
        "", "## 评估口径", "",
        "- 模型和预处理仅用原训练集重拟合。锁定配置在验证集重算的分数和前 30% 名单与第四阶段相符。"
        "保留集分数与排名先写入文件，再关联保留集的实验标签计算效果。",
        "- 每种策略使用同一个覆盖比例，平分按客户编号升序。逐项区间采用独立客户、非合并方差近似。"
        "配对区间考虑两份触达名单重叠，并以给定名单为条件。",
        "- 策略采用门槛是模型相对两条基线的配对区间下界均大于零。"
        "结果衡量观察到的购买率差，因果解释仍取决于实验分配条件。利润评估需实际短信成本和每笔增量购买毛利。", "",
        "[评估锁定文件](metadata/evaluation_lock.json) · [保留集策略图](figures/holdout_uplift.png) · [结果索引](README.md)", "",
    ]
    (out / "最终保留集评估报告.md").write_text("\n".join(text), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    out = args.output
    base = run_path(str(ROOT / "scripts/04_uplift_baselines.py"))
    require = base["require"]
    lock_path = out / "metadata/evaluation_lock.json"
    lock = read_json(lock_path)
    require(lock["candidate"] == "t_logistic" and lock["comparators"] == ["random", "rfm"] and
            lock["reach_pct"] == 30 and lock["fit_split"] == "train" and lock["evaluation_split"] == "holdout",
            "Unexpected evaluation plan")
    for path, expected in lock["sha256"].items():
        require(sha256(ROOT / path) == expected, f"Locked file changed: {path}")
    for key, version in (("numpy", np.__version__), ("pandas", pd.__version__),
                         ("scikit_learn", sklearn.__version__)):
        require(lock["model"][key] == version, f"Model runtime differs: {key}")

    score_path, replay = score(out, lock, base)
    metrics, comparisons = evaluate(score_path, lock, base)
    names = base["NAMES"]
    metrics.insert(0, "label", metrics.index.map(names))
    metrics.to_csv(out / "tables/holdout_at30.csv", encoding="utf-8-sig")
    comparisons.to_csv(out / "tables/holdout_candidate_vs_baselines.csv", index=False, encoding="utf-8-sig")
    passed = bool((comparisons.ci_low_pp > 0).all())
    customers = read_json(out / "metadata/holdout_features.json")["customers"]
    result = dict(
        candidate=lock["candidate"], customers=customers, reach_pct=lock["reach_pct"],
        selected_per_policy=lock["selected_count"], passes_prespecified_rule=passed,
        validation_replay_max_abs_score_diff=replay, locked_plan_sha256=sha256(lock_path),
        score_file_sha256=sha256(score_path),
    )
    (out / "metadata/evaluation_summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    report(out, metrics, comparisons, lock, passed, names, customers)
    print(metrics.to_string())
    print(comparisons.to_string(index=False))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
