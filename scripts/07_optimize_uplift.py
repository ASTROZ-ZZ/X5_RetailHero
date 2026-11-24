#!/usr/bin/env python3
"""Compare a fixed set of uplift variants by repeated, honest development-fold scoring."""

import argparse
import hashlib
import json
from pathlib import Path
from runpy import run_path

import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/07_uplift_optimization"
NEW = ["recency_to_gap", "order_change_14d"]
NAMES = {
    "base_t": "原 T-Learner",
    "behavior_t": "T-Learner 加行为特征",
    "interaction_s": "正则化 S-Learner 加行为特征",
}
REPEAT_SEEDS = (20261125, 20261126, 20261127)
RANDOM_SEEDS = tuple(range(20261116, 20261128))
FOLDS = 5
PCT = 30
INTERACTION_SCALE = .25


def require(ok, message):
    if not ok:
        raise ValueError(message)


def development(out, base):
    meta = json.loads((out / "metadata/behavior_features.json").read_text())
    split_path = ROOT / "results/01_data_audit/splits/split_assignments.csv"
    split = pd.read_csv(split_path, dtype=str).set_index("client_id", verify_integrity=True).split
    require(hashlib.sha256(split_path.read_bytes()).hexdigest() == meta["split_sha256"], "Split differs")
    paths = {
        "train": ROOT / "results/02_customer_analysis/tables/customer_features.csv",
        "validation": ROOT / "results/04_uplift_baselines/tables/validation_features.csv",
    }
    expected = set(split[split.isin(paths)].index)
    fields = ["client_id", *base["NUMERIC"], *base["CATEGORICAL"]]
    frames = []
    for name, path in paths.items():
        frame = pd.read_csv(path, usecols=fields, dtype={"client_id": str})
        require(frame.client_id.is_unique and set(frame.client_id) == set(split[split.eq(name)].index),
                f"Feature population differs: {name}")
        frames.append(frame)
    behavior_path = out / "tables/behavior_features.csv"
    require(meta["status"] == "PASS" and hashlib.sha256(behavior_path.read_bytes()).hexdigest() ==
            meta["behavior_features_sha256"], "Behavior features differ from metadata")
    behavior = pd.read_csv(behavior_path, usecols=["client_id", *NEW], dtype={"client_id": str})
    require(behavior.client_id.is_unique and set(behavior.client_id) == expected, "Behavior population differs")
    labels = pd.read_csv(ROOT / "data/uplift_train.csv", dtype={"client_id": str})
    labels = labels[labels.client_id.isin(expected)]
    require(labels.client_id.is_unique and set(labels.client_id) == expected and
            labels[["treatment_flg", "target"]].isin([0, 1]).all().all(), "Invalid development labels")
    frame = pd.concat(frames, ignore_index=True).merge(behavior, on="client_id", validate="one_to_one")
    return frame.merge(labels, on="client_id", validate="one_to_one").sort_values("client_id").reset_index(drop=True)


def fit_fold(train, test, base):
    original, _ = base["predict"](train, test, ["t_logistic"])
    numeric = [*base["NUMERIC"], *NEW]
    categorical = base["CATEGORICAL"]
    preprocessor = ColumnTransformer([
        ("numeric", make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler()), numeric),
        ("category", make_pipeline(SimpleImputer(strategy="constant", fill_value="__UNKNOWN__"),
                                   OneHotEncoder(handle_unknown="ignore", sparse_output=False)), categorical),
    ])
    x, v = preprocessor.fit_transform(train), preprocessor.transform(test)
    treatment, outcome = train.treatment_flg.to_numpy(), train.target.to_numpy()

    def logistic():
        return LogisticRegression(C=1.0, max_iter=500, random_state=base["SEED"])

    predictions = []
    for arm in (0, 1):
        selected = treatment == arm
        predictions.append(logistic().fit(x[selected], outcome[selected]).predict_proba(v)[:, 1])

    modifiers = [numeric.index(name) for name in NEW]

    def s_design(matrix, t):
        # Scaling the standardized interaction columns increases their effective L2 penalty.
        return np.column_stack([matrix, t, matrix[:, modifiers] * t[:, None] * INTERACTION_SCALE])

    single = logistic().fit(s_design(x, treatment), outcome)
    scores = {
        "base_t": original["t_logistic"],
        "behavior_t": predictions[1] - predictions[0],
        "interaction_s": single.predict_proba(s_design(v, np.ones(len(v))))[:, 1] -
                         single.predict_proba(s_design(v, np.zeros(len(v))))[:, 1],
    }
    require(all(np.isfinite(values).all() for values in scores.values()), "Non-finite fold score")
    return scores


def estimate(order, t, y):
    k = len(order) * PCT // 100
    selected = order[:k]
    arms = t[selected]
    n1 = int(arms.sum())
    n0 = k - n1
    require(min(n0, n1) > 0, "A selected arm is empty")
    y1 = int(y[selected][arms == 1].sum())
    y0 = int(y[selected][arms == 0].sum())
    return dict(selected=k, sms_n=n1, control_n=n0, sms_buyers=y1, control_buyers=y0,
                uplift_pp=100 * (y1/n1-y0/n0))


def experiments(frame, base):
    ids = frame.client_id.to_numpy()
    strata = 2 * frame.treatment_flg + frame.target
    random_hashes = {
        seed: np.array([int.from_bytes(hashlib.sha256(f"{seed}:{i}".encode()).digest()[:8], "big")
                        for i in ids], dtype=np.uint64)
        for seed in RANDOM_SEEDS
    }
    model_rows, random_rows, records = [], [], []
    for repeat, seed in enumerate(REPEAT_SEEDS, 1):
        cv = StratifiedKFold(n_splits=FOLDS, shuffle=True, random_state=seed)
        for fold, (fit, test) in enumerate(cv.split(ids, strata), 1):
            training, evaluation = frame.iloc[fit], frame.iloc[test]
            scores = fit_fold(training, evaluation, base)
            t, y = evaluation.treatment_flg.to_numpy(), evaluation.target.to_numpy()
            block = dict(repeat=repeat, fold=fold, fold_customers=len(test))
            random_effects = []
            for random_seed, hashes in random_hashes.items():
                order = np.argsort(hashes[test], kind="stable")
                result = estimate(order, t, y)
                random_effects.append(result["uplift_pp"])
                random_rows.append(dict(**block, random_seed=random_seed, **result))
            reference = float(np.mean(random_effects))
            fold_models = []
            for key, values in scores.items():
                order = base["rank"](ids[test], key, values)
                result = estimate(order, t, y)
                fold_models.append(dict(**block, model=key, random_mean_pp=reference,
                                        vs_random_pp=result["uplift_pp"]-reference, **result))
            base_effect = fold_models[0]["uplift_pp"]
            for row in fold_models:
                row["vs_base_t_pp"] = row["uplift_pp"] - base_effect
                model_rows.append(row)
            records.append(pd.DataFrame({"client_id": ids[test], "repeat": repeat, "fold": fold, **scores}))
            print(f"Repeat {repeat}, fold {fold}: done", flush=True)
    return pd.DataFrame(model_rows), pd.DataFrame(random_rows), pd.concat(records, ignore_index=True)


def summarize(folds):
    grouped = folds.groupby("model", sort=False)
    overview = grouped.agg(
        mean_uplift_pp=("uplift_pp", "mean"), mean_vs_random_pp=("vs_random_pp", "mean"),
        sd_vs_random_pp=("vs_random_pp", "std"), min_vs_random_pp=("vs_random_pp", "min"),
        max_vs_random_pp=("vs_random_pp", "max"), mean_vs_base_t_pp=("vs_base_t_pp", "mean"),
    )
    overview["folds_positive_vs_random"] = grouped.vs_random_pp.apply(lambda v: int((v > 0).sum()))
    overview["folds_positive_vs_base_t"] = grouped.vs_base_t_pp.apply(lambda v: int((v > 0).sum()))
    repeats = folds.groupby(["model", "repeat"], sort=False)[["uplift_pp", "vs_random_pp", "vs_base_t_pp"]].mean()
    overview["repeats_positive_vs_base_t"] = repeats.vs_base_t_pp.groupby("model").apply(lambda v: int((v > 0).sum()))
    return overview, repeats.reset_index()


def report(path, overview, repeats, n, feature):
    best = overview.mean_vs_random_pp.idxmax()
    count = FOLDS * len(REPEAT_SEEDS)
    lead = overview.loc[best]
    lines = [
        "# X5 Uplift 优化诊断", "",
        f"仅在原训练与验证组成的 {n:,} 位开发客户上，用 {len(REPEAT_SEEDS)} 次重复、每次 {FOLDS} 折比较三种模型。"
        f"按 30% 触达下的平均领先幅度，**{NAMES[best]}**排名第一，平均比随机基线高 "
        f"**{lead.mean_vs_random_pp:+.2f} 个百分点**。", "",
        "| 模型 | 平均 Uplift@30% | 平均领先随机 | 领先随机的折数 | 平均领先原模型 | 领先原模型的折数 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for key, r in overview.iterrows():
        lines.append(f"| {NAMES[key]} | {r.mean_uplift_pp:+.2f} | {r.mean_vs_random_pp:+.2f} | "
                     f"{int(r.folds_positive_vs_random)}/{count} | {r.mean_vs_base_t_pp:+.2f} | "
                     f"{'—' if key == 'base_t' else str(int(r.folds_positive_vs_base_t))+'/'+str(count)} |")
    lines += [
        "", "表中差值单位为百分点。每折随机基线使用同一批评估客户和相同触达比例，取 12 个预先固定种子下的平均结果。"
        "各折及重复之间共享开发数据，折数和标准差用于描述稳定性。", "",
        "## 两项特征与模型约束", "",
        f"- 超出个人购买节奏的程度为距上次购买天数除以个人复购间隔中位数。"
        f"无个人间隔的 {feature['missing_recency_to_gap']:,} 人保留缺失，模型在每个训练折内填补并保留缺失标记。",
        f"- 订单变化为最近 14 天订单数减前 14 天订单数。窗口分别是 "
        f"`[{', '.join(feature['recent_interval'])})` 和 `[{', '.join(feature['previous_interval'])})`，"
        "订单按客户和交易编号去重。",
        "- 原模型与增强 T-Learner 使用相同逻辑回归配置。S-Learner 在合并数据上拟合共同主效应，"
        "只允许短信与两个新特征交互，并缩小交互列的尺度以加强 L2 收缩。所有模型配置固定，填补、标准化和编码在每个训练折重拟合。", "",
        "## 如何使用结果", "",
    ]
    if best == "base_t":
        lines.append("原模型在这轮诊断中平均表现最好，当前离线交付继续采用原模型。")
    else:
        wins = int(lead.repeats_positive_vs_base_t)
        lines.append(f"{NAMES[best]}在 {wins}/{len(REPEAT_SEEDS)} 次重复的平均结果上优于原模型，"
                     f"平均差为 {lead.mean_vs_base_t_pp:+.2f} 个百分点。")
        if wins < len(REPEAT_SEEDS):
            lines.append("各次重复下的改进方向不一致，本轮结果不足以支持用它替换原模型。")
    lines += [
        "这轮交叉验证复用了曾用于开发和选择策略的客户，结果用于判断优化方向。"
        "原保留集已用于上一阶段的独立评价，原结论继续作为记录。"
        "优化模型如用于实际触达，需要在新样本上按相同预算直接比较策略。", "",
        "[重复结果图](figures/repeated_cv_uplift.png) · [结果索引](README.md)", "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT)
    out = parser.parse_args().output
    base = run_path(str(ROOT / "scripts/04_uplift_baselines.py"))
    frame = development(out, base)
    plan = dict(
        population=["train", "validation"], repeat_seeds=REPEAT_SEEDS, folds=FOLDS,
        stratification="treatment_flg × target", reach_pct=PCT, random_seeds=RANDOM_SEEDS,
        variants=list(NAMES), new_features=NEW, c=1.0, interaction_scale=INTERACTION_SCALE,
        model_selection="Highest average fold Uplift@30% difference versus fixed-seed random average",
    )
    (out / "metadata/cv_plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    folds, random, scores = experiments(frame, base)
    require(len(scores) == len(frame) * len(REPEAT_SEEDS) and
            not scores.duplicated(["repeat", "client_id"]).any(), "OOF prediction coverage differs")
    overview, repeats = summarize(folds)
    for name, table in [("fold_metrics", folds), ("random_fold_metrics", random),
                        ("model_summary", overview.reset_index()), ("repeat_summary", repeats)]:
        table.to_csv(out / "tables" / f"{name}.csv", index=False, encoding="utf-8-sig")
    scores.to_csv(out / "tables/fold_scores.csv.gz", index=False,
                  compression={"method":"gzip","compresslevel":4,"mtime":0})
    best = overview.mean_vs_random_pp.idxmax()
    metadata = dict(
        customers=len(frame), oof_score_rows=len(scores), best_by_mean_vs_random=best,
        model_results=overview.to_dict("index"), numpy=np.__version__, pandas=pd.__version__,
        scikit_learn=sklearn.__version__,
    )
    payload = json.dumps(metadata, indent=2)
    (out / "metadata/cv_summary.json").write_text(payload + "\n")
    report(out / "Uplift优化诊断报告.md", overview, repeats, len(frame),
           json.loads((out / "metadata/behavior_features.json").read_text()))
    print(payload, flush=True)


if __name__ == "__main__":
    main()
