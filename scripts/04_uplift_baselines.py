#!/usr/bin/env python3
"""Fit fixed baseline policies on train and compare them on validation."""

import argparse
import hashlib
import json
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/04_uplift_baselines"
SEED = 20261116
PERCENTAGES = list(range(5, 101, 5))
NUMERIC = [
    "frequency", "recency_days", "monetary", "avg_order_value", "purchase_days",
    "median_repurchase_gap_days", "top_level_2_line_share", "distinct_known_level_2",
]
CATEGORICAL = ["top_level_2_by_lines"]
NAMES = {
    "random": "随机排序",
    "rfm": "RFM 规则",
    "purchase_probability": "普通购买概率",
    "s_logistic": "S-Learner 逻辑回归",
    "t_logistic": "T-Learner 逻辑回归",
    "t_hist_gradient": "T-Learner 梯度提升树",
}
UPLIFT_MODELS = ("s_logistic", "t_logistic", "t_hist_gradient")
Z95 = NormalDist().inv_cdf(.975)
TREE_PARAMS = dict(
    max_iter=120, learning_rate=.05, max_leaf_nodes=12, min_samples_leaf=300,
    l2_regularization=1.0, early_stopping=False, random_state=SEED,
)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def inputs(out):
    split_file = ROOT / "results/01_data_audit/splits/split_assignments.csv"
    split = pd.read_csv(split_file, dtype=str).set_index("client_id", verify_integrity=True)["split"]
    fingerprint = hashlib.sha256(split_file.read_bytes()).hexdigest()
    stage02 = ROOT / "results/02_customer_analysis"
    feature_train = json.loads((stage02 / "metadata/analysis_summary.json").read_text())
    feature_valid = json.loads((out / "metadata/validation_features.json").read_text())
    require(fingerprint == feature_train["split_file_sha256"] == feature_valid["split_sha256"],
            "Fixed split differs from feature-generation records")
    for key in ("reference_date", "thresholds"):
        require(feature_train[key] == feature_valid[key], f"Feature definitions differ: {key}")
    labels = pd.read_csv(ROOT / "data/uplift_train.csv", dtype={"client_id": str})
    feature_paths = {
        "train": stage02 / "tables/customer_features.csv",
        "validation": out / "tables/validation_features.csv",
    }
    frames = {}
    for name, path in feature_paths.items():
        expected = set(split[split.eq(name)].index)
        frame = pd.read_csv(path, dtype={"client_id": str}, usecols=["client_id", *NUMERIC, *CATEGORICAL])
        require(frame.client_id.is_unique and set(frame.client_id) == expected, f"Feature population differs: {name}")
        label = labels[labels.client_id.isin(expected)]
        require(label.client_id.is_unique and set(label.client_id) == expected, f"Label population differs: {name}")
        require(label[["target", "treatment_flg"]].isin([0, 1]).all().all(), f"Invalid label: {name}")
        frames[name] = frame.merge(label, on="client_id", validate="one_to_one").sort_values("client_id")
    return frames["train"], frames["validation"], fingerprint


def predict(train, valid, policies=None):
    policies = set(NAMES if policies is None else policies)
    require(policies and policies <= NAMES.keys(), "Unknown or empty policy selection")
    preprocessor = ColumnTransformer([
        ("numeric", make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler()), NUMERIC),
        ("category", make_pipeline(SimpleImputer(strategy="constant", fill_value="__UNKNOWN__"),
                                   OneHotEncoder(handle_unknown="ignore", sparse_output=False)), CATEGORICAL),
    ])
    x = preprocessor.fit_transform(train)
    v = preprocessor.transform(valid)
    t, y = train.treatment_flg.to_numpy(), train.target.to_numpy()
    scores = {}
    ids = valid.client_id.to_numpy()
    if "random" in policies:
        scores["random"] = np.array([hashlib.sha256(f"{SEED}:{i}".encode()).hexdigest() for i in ids])
    if "rfm" in policies:
        rfm = np.zeros(len(valid))
        for key, direction in [("recency_days", -1), ("frequency", 1), ("monetary", 1)]:
            values = np.sort(direction * train[key].to_numpy())
            rfm += np.searchsorted(values, direction * valid[key].to_numpy(), side="right") / len(values)
        scores["rfm"] = rfm / 3

    def logistic():
        return LogisticRegression(C=1.0, max_iter=500, random_state=SEED)

    if "purchase_probability" in policies:
        scores["purchase_probability"] = logistic().fit(x, y).predict_proba(v)[:, 1]
    if "s_logistic" in policies:
        sf = logistic().fit(np.column_stack([x, t]), y)
        sends = sf.predict_proba(np.column_stack([v, np.ones(len(v))]))[:, 1]
        no_sends = sf.predict_proba(np.column_stack([v, np.zeros(len(v))]))[:, 1]
        scores["s_logistic"] = sends - no_sends
    for key, model in [("t_logistic", logistic), ("t_hist_gradient", lambda: HistGradientBoostingClassifier(**TREE_PARAMS))]:
        if key not in policies:
            continue
        probabilities = []
        for arm in (0, 1):
            mask = t == arm
            probabilities.append(model().fit(x[mask], y[mask]).predict_proba(v)[:, 1])
        scores[key] = probabilities[1] - probabilities[0]
    for key, score in scores.items():
        if key != "random":
            require(np.isfinite(score).all(), f"Non-finite score: {key}")
    return scores, x.shape[1]


def rank(ids, key, score):
    # Validation IDs start in ascending order, so stable sorting preserves ties.
    if key == "random":
        return np.argsort(score, kind="stable")
    return np.lexsort((ids, -score))


def policy_curve(key, order, treatment, target, percentages=PERCENTAGES):
    n = len(order)
    t, y = treatment[order], target[order]
    sms = np.cumsum(t)
    sms_buy = np.cumsum(y * t)
    control_buy = np.cumsum(y * (1 - t))
    curve = []
    for pct in percentages:
        k = n * pct // 100
        n1, y1, y0 = (int(a[k - 1]) for a in (sms, sms_buy, control_buy))
        n0 = k - n1
        require(min(n0, n1) > 0, f"An arm is empty at {key}, {pct}%")
        p0, p1 = y0 / n0, y1 / n1
        effect = p1 - p0
        se = np.sqrt(p0 * (1 - p0) / n0 + p1 * (1 - p1) / n1)
        curve.append(dict(
            policy=key, reach_pct=pct, selected=k, sms_n=n1, control_n=n0, sms_buyers=y1,
            control_buyers=y0, sms_rate=p1, control_rate=p0, uplift_pp=100 * effect,
            ci_low_pp=100 * (effect-Z95*se), ci_high_pp=100 * (effect+Z95*se),
            normalized_gain_pp=100 * (y1 - y0 * n1 / n0) / sms[-1],
        ))
    return pd.DataFrame(curve)


def area(x, y):
    return float(np.sum(np.diff(x) * (y[1:] + y[:-1]) * .5))


def paired_at30(winner, rankings, treatment, target, metrics,
                comparators=("random", "rfm", "purchase_probability")):
    n = len(treatment)
    k = n * 30 // 100

    def contributions(policy):
        selected = rankings[policy][:k]
        out = np.zeros(n)
        for arm, sign in [(0, -1), (1, 1)]:
            ids = selected[treatment[selected] == arm]
            out[ids] = sign * (target[ids] - target[ids].mean()) / len(ids)
        return out

    result = []
    for comparator in comparators:
        if comparator == winner:
            continue
        delta = float(metrics.loc[winner, "uplift_pp"] - metrics.loc[comparator, "uplift_pp"])
        se = float(100 * np.linalg.norm(contributions(winner) - contributions(comparator)))
        result.append(dict(
            policy=winner, comparator=comparator, difference_pp=delta,
            ci_low_pp=delta-Z95*se, ci_high_pp=delta+Z95*se,
            overlap_pct=100 * np.intersect1d(rankings[winner][:k], rankings[comparator][:k]).size / k,
        ))
    return pd.DataFrame(result)


def report(out, metrics, comparisons, candidate, best, validation_count):
    top = metrics.loc[best]
    chosen = metrics.loc[candidate]
    lines = [
        "# X5 Uplift 基线验证", "",
        f"验证集 {validation_count:,} 人中，每种策略固定选前 {int(top.selected):,} 人。按 Uplift@30% 点估计，"
        f"六种策略中最高的是 **{NAMES[best]}**（{top.uplift_pp:+.2f} 个百分点）。"
        f"三个 Uplift 模型中的首选候选为 **{NAMES[candidate]}**（{chosen.uplift_pp:+.2f} 个百分点）。", "",
        "| 策略 | 短信组购买率 | 对照组购买率 | Uplift@30%（百分点） | 95% CI | AUUC | Qini |",
        "|---|---:|---:|---:|---|---:|---:|",
    ]
    for policy, row in metrics.iterrows():
        lines.append(f"| {NAMES[policy]} | {row.sms_rate:.2%} | {row.control_rate:.2%} | {row.uplift_pp:+.2f} | "
                     f"[{row.ci_low_pp:+.2f}, {row.ci_high_pp:+.2f}] | {row.auuc:.3f} | {row.qini:.3f} |")
    lines += ["", "## 首选 Uplift 候选与基线的直接对比", "",
              "| 对比基线 | 候选领先幅度（百分点） | 95% CI | 前 30% 名单重叠 |",
              "|---|---:|---|---:|"]
    for r in comparisons.itertuples():
        lines.append(f"| {NAMES[r.comparator]} | {r.difference_pp:+.2f} | "
                     f"[{r.ci_low_pp:+.2f}, {r.ci_high_pp:+.2f}] | {r.overlap_pct:.1f}% |")
    clear = int((comparisons.ci_low_pp > 0).sum())
    lines += [
        "",
        f"与三条对照策略比较，候选有 {clear} 条配对区间完全高于零。"
        "候选按同一个验证集上的最高模型点估计筛出，区间为固定名单条件下的探索性近似，未做筛选校正。",
        "验证结果支持将候选带入最终保留集，与随机排序和 RFM 规则在同样的触达比例下做独立评价。", "",
        "## 口径", "",
        "- 在训练集拟合缺失填补、标准化、品类编码和全部模型。验证集复用相同的历史特征口径。预测只用历史特征，S-Learner 分别指定两种短信状态来计算概率差。",
        "- 随机排序使用固定种子哈希。RFM 规则使用训练集经验分位数，对近期购买、订单次数和消费金额等权打分。购买概率基线在全体训练客户拟合购买，无短信输入。",
        "- 前 30% 按本地规则向下取整，分数并列按客户编号升序。实际短信标记与购买结果只用于相应的模型训练和验证评价。",
        "- 曲线按每 5% 采样，用梯形法积分。AUUC 为累计人群购买率差（百分点）对覆盖比例的面积，起点设 0。Qini 用累计增量购买人数除以验证集短信组总人数并换算为百分点，再减去起点和终点间的直线后积分。",
        "- 策略间区间利用相同验证客户和名单重叠，通过购买率差的一阶方差近似计算。因果和利润解释仍分别依赖实验分配条件与成本毛利数据。",
        "", "[触达比例对照图](figures/validation_uplift.png) · [复现与结果索引](README.md)", "",
    ]
    (out / "Uplift基线验证报告.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    out = args.output
    train, valid, split_hash = inputs(out)
    scores, n_features = predict(train, valid)
    ids = valid.client_id.to_numpy()
    target, treatment = valid.target.to_numpy(), valid.treatment_flg.to_numpy()
    curves, rankings, rows = [], {}, []
    for key, score in scores.items():
        order = rank(ids, key, score)
        rankings[key] = order
        curve = policy_curve(key, order, treatment, target)
        x = np.r_[0, curve.reach_pct.to_numpy() / 100]
        uplift = np.r_[0, curve.uplift_pp.to_numpy()]
        gain = np.r_[0, curve.normalized_gain_pp.to_numpy()]
        row = curve.loc[curve.reach_pct.eq(30)].iloc[0].to_dict()
        row.update(label=NAMES[key], auuc=area(x, uplift), qini=area(x, gain - x * gain[-1]))
        curves.append(curve)
        rows.append(row)
    metrics = pd.DataFrame(rows).set_index("policy").sort_values("uplift_pp", ascending=False)
    best = metrics.index[0]
    candidate = metrics[metrics.index.isin(UPLIFT_MODELS)].index[0]
    comparisons = paired_at30(candidate, rankings, treatment, target, metrics)
    tables = out / "tables"
    metrics.to_csv(tables / "validation_at30.csv", encoding="utf-8-sig")
    pd.concat(curves, ignore_index=True).to_csv(tables / "validation_curves.csv", index=False, encoding="utf-8-sig")
    comparisons.to_csv(tables / "candidate_vs_baselines.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame({"client_id": ids, **scores}).to_csv(
        tables / "validation_scores.csv.gz", index=False, compression={"method": "gzip", "mtime": 0}
    )
    metadata = dict(
        training_customers=len(train), validation_customers=len(valid), seed=SEED, split_sha256=split_hash,
        candidate=candidate, highest_validation_at30=best, trained_model_candidates=list(UPLIFT_MODELS),
        numeric_features=NUMERIC, categorical_features=CATEGORICAL, encoded_feature_count=n_features,
        tree_parameters=TREE_PARAMS, logistic_C=1.0, numpy=np.__version__, pandas=pd.__version__,
        scikit_learn=sklearn.__version__,
    )
    (out / "metadata/baseline_summary.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    report(out, metrics, comparisons, candidate, best, len(valid))
    print(metrics[["label", "uplift_pp", "ci_low_pp", "ci_high_pp", "auuc", "qini"]].to_string(), flush=True)
    print(comparisons.to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
