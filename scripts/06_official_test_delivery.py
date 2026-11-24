#!/usr/bin/env python3
"""Refit the locked T-Learner on all labeled customers and export official scores."""

import argparse
import hashlib
import json
from pathlib import Path
from runpy import run_path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd
import sklearn


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/06_offline_delivery"
STAGE02 = ROOT / "results/02_customer_analysis"
STAGE03 = ROOT / "results/03_sms_experiment"
STAGE04 = ROOT / "results/04_uplift_baselines"
STAGE05 = ROOT / "results/05_holdout_evaluation"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def labeled_data(base, lock):
    require = base["require"]
    splits = pd.read_csv(ROOT / "results/01_data_audit/splits/split_assignments.csv", dtype=str)
    require(splits.client_id.notna().all() and splits.client_id.is_unique and
            set(splits.split) == {"train", "validation", "holdout"}, "Invalid fixed split")
    labels = pd.read_csv(ROOT / "data/uplift_train.csv", dtype={"client_id": str})
    require(list(labels) == ["client_id", "treatment_flg", "target"] and labels.client_id.is_unique and
            labels[["treatment_flg", "target"]].isin([0, 1]).all().all() and
            set(labels.client_id) == set(splits.client_id), "Experiment labels do not cover the fixed split")
    fields = ["client_id", *base["NUMERIC"], *base["CATEGORICAL"]]
    expected = read_json(STAGE02 / "metadata/analysis_summary.json")
    sources = {
        "train": STAGE02 / "tables/customer_features.csv",
        "validation": STAGE04 / "tables/validation_features.csv",
        "holdout": STAGE05 / "tables/holdout_features.csv",
    }
    for root, split in [(STAGE04, "validation"), (STAGE05, "holdout")]:
        manifest = read_json(root / f"metadata/{split}_features.json")
        require(manifest["status"] == "PASS" and manifest["split"] == split and
                manifest["split_sha256"] == lock["model"]["split_sha256"], f"Invalid {split} extraction")
        require(all(expected[key] == manifest[key] for key in ("reference_date", "thresholds")),
                f"Feature definitions differ: {split}")
    frames = []
    for split, path in sources.items():
        frame = pd.read_csv(path, usecols=fields, dtype={"client_id": str})
        require(frame.client_id.is_unique and set(frame.client_id) == set(splits.loc[splits.split.eq(split), "client_id"]),
                f"Wrong customers in {split} features")
        frames.append(frame)
    combined = pd.concat(frames, ignore_index=True).merge(labels, validate="one_to_one", on="client_id")
    require(len(combined) == len(labels), "Combined feature population differs")
    return combined.sort_values("client_id"), fields


def official_features(out, require, fields, labeled_ids):
    metadata = read_json(out / "metadata/official_test_features.json")
    expected = read_json(STAGE02 / "metadata/analysis_summary.json")
    test_file = ROOT / "data/uplift_test.csv"
    template = ROOT / "data/uplift_sample_submission.csv"
    features_path = out / "tables/official_test_features.csv"
    require(metadata["status"] == "PASS" and
            metadata["split_sha256"] == expected["split_file_sha256"] and
            all(metadata[key] == expected[key] for key in ("reference_date", "thresholds", "history_start", "history_end")),
            "Official test feature definitions differ")
    require(metadata["official_test_sha256"] == sha256(test_file) and
            metadata["features_sha256"] == sha256(features_path), "Official test inputs differ from extraction")
    test = pd.read_csv(test_file, dtype=str)
    order = pd.read_csv(template, usecols=["client_id"], dtype=str).client_id
    features = pd.read_csv(features_path, usecols=fields, dtype={"client_id": str})
    require(test.client_id.notna().all() and test.client_id.is_unique and order.notna().all() and order.is_unique and
            features.client_id.is_unique and set(test.client_id) == set(order) == set(features.client_id),
            "Test, feature and template ID populations do not agree")
    require(set(order).isdisjoint(labeled_ids), "Test customers overlap with training")
    require(len(features) == metadata["customers"], "Test feature row count differs")
    return features.set_index("client_id").loc[order].reset_index()


def write_report(out, metadata, holdout_summary):
    experiment = read_json(STAGE03 / "metadata/experiment_summary.json")["overall"]
    stage02_meta = read_json(STAGE02 / "metadata/analysis_summary.json")
    val = pd.read_csv(STAGE04 / "tables/validation_at30.csv").set_index("policy")
    hold = pd.read_csv(STAGE05 / "tables/holdout_at30.csv").set_index("policy")
    paired = pd.read_csv(STAGE05 / "tables/holdout_candidate_vs_baselines.csv").set_index("comparator")
    candidate = metadata["candidate"]
    t = paired.loc["random"]
    lines = [
        "# X5 RetailHero 项目总结", "",
        f"已为 {metadata['scored_customers']:,} 位官方测试客户交付离线预测。T-Learner 逻辑回归使用全部 "
        f"{metadata['labeled_customers']:,} 位有标签客户重训，模型类型、输入特征和超参数沿用锁定配置。"
        "保留集的业务结论仍以重训前的独立评估为准。", "",
        "## 从数据到策略", "",
        f"- 客户分析以 {stage02_meta['training_customers']:,} 位训练客户为范围，归并出 "
        f"{stage02_meta['training_orders']:,} 笔历史订单，再计算 RFM、客单价、复购间隔和品类偏好。",
        f"- 短信实验中，训练集短信组购买率为 {experiment['sms_rate']:.2%}，对照组为 "
        f"{experiment['control_rate']:.2%}，观察到的差值为 {experiment['difference_pp']:+.2f} 个百分点。"
        "随机分配协议仍待核实。",
        "- 基线阶段在验证集比较六条策略，选择 T-Learner 逻辑回归进入保留集。保留集对照策略和 30% 触达比例在读取结果前锁定。",
        "", "| 策略 | 验证集 Uplift@30% | 最终保留集 Uplift@30% |",
        "|---|---:|---:|",
    ]
    for key in (candidate, "random", "rfm"):
        lines.append(f"| {val.loc[key,'label']} | {val.loc[key,'uplift_pp']:+.2f} 个百分点 | {hold.loc[key,'uplift_pp']:+.2f} 个百分点 |")
    lines += [
        "",
        f"保留集上，T-Learner 比随机排序高 **{t.difference_pp:+.2f} 个百分点**"
        f"（配对 95% CI [{t.ci_low_pp:+.2f}, {t.ci_high_pp:+.2f}]）。"
        + ("锁定的策略采用门槛已满足。" if holdout_summary["passes_prespecified_rule"] else
           "区间跨零，结果未达到同时优于两条基线的锁定采用门槛。真实投放仍需新的随机实验确认。"),
        "", "## 官方测试交付", "",
        "- 使用历史订单、消费金额、最近购买间隔及品类等同口径特征。正式重训会在全部有标签客户上重新拟合填补、标准化和编码。",
        "- 每个 Uplift 分数等于短信组模型的预测购买概率减去对照组模型的预测购买概率。"
        "官方测试名单无购买或处理标签，本阶段验证覆盖、顺序、格式和数值。",
        "- 输出按提交样例的客户顺序排列。文件可用于离线竞赛交付，策略商用判断仍基于独立实验和实际成本收益。", "",
        "[预测文件](tables/uplift_submission.csv) · [交付与复现索引](README.md) · "
        "[保留集报告](../05_holdout_evaluation/最终保留集评估报告.md)", "",
    ]
    (out / "X5项目总结.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT)
    out = parser.parse_args().output
    lock_path = STAGE05 / "metadata/evaluation_lock.json"
    lock = read_json(lock_path)
    holdout_summary = read_json(STAGE05 / "metadata/evaluation_summary.json")
    base = run_path(str(ROOT / "scripts/04_uplift_baselines.py"))
    require = base["require"]
    require(lock["candidate"] == holdout_summary["candidate"] == "t_logistic" and
            holdout_summary["locked_plan_sha256"] == sha256(lock_path), "Model differs from completed holdout evaluation")
    for filename, expected in lock["sha256"].items():
        require(sha256(ROOT / filename) == expected, f"Locked file changed: {filename}")
    for key, version in (("numpy", np.__version__), ("pandas", pd.__version__), ("scikit_learn", sklearn.__version__)):
        require(lock["model"][key] == version, f"Model runtime differs: {key}")
    train, fields = labeled_data(base, lock)
    customers = official_features(out, require, fields, set(train.client_id))
    scores, encoded = base["predict"](train, customers, [lock["candidate"]])
    uplift = scores[lock["candidate"]]
    require(len(uplift) == len(customers) and np.isfinite(uplift).all() and
            ((uplift >= -1) & (uplift <= 1)).all(), "Missing or out-of-range official scores")
    submission = pd.DataFrame({"client_id": customers.client_id, "uplift": uplift})
    with TemporaryDirectory(prefix=".submission-", dir=out) as work:
        staged = Path(work) / "uplift_submission.csv"
        submission.to_csv(staged, index=False, encoding="utf-8")
        digest = sha256(staged)
        staged.replace(out / "tables" / staged.name)
    metadata = dict(
        status="PASS", candidate=lock["candidate"], labeled_customers=len(train),
        labeled_control=int(train.treatment_flg.eq(0).sum()), labeled_sms=int(train.treatment_flg.eq(1).sum()),
        scored_customers=len(submission), encoded_feature_count=encoded,
        order="uplift_sample_submission.csv client_id order",
        prediction_sha256=digest, evaluation_lock_sha256=sha256(lock_path),
        score_range=[float(uplift.min()), float(uplift.max())],
        holdout_passes_prespecified_rule=holdout_summary["passes_prespecified_rule"],
    )
    (out / "metadata/submission_summary.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    write_report(out, metadata, holdout_summary)
    print(json.dumps(metadata, indent=2), flush=True)


if __name__ == "__main__":
    main()
