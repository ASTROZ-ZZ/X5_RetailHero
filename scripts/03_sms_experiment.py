#!/usr/bin/env python3
"""Estimate SMS purchase-rate differences on the fixed training split."""

import argparse
from math import erfc, exp, sqrt
from pathlib import Path
from statistics import NormalDist
import json

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "results/03_sms_experiment"
SEGMENTS = ("高价值活跃", "高价值待唤醒", "近期活跃", "低近期活跃", "其他客户")
BALANCE = {
    "recency_days": "最近购买间隔",
    "frequency": "订单次数",
    "monetary": "累计消费",
    "avg_order_value": "客单价",
    "purchase_days": "购买天数",
    "median_repurchase_gap_days": "个人复购间隔中位数",
    "distinct_known_level_2": "已知二级品类数",
    "top_level_2_line_share": "首选品类明细行占比",
}
Z95 = NormalDist().inv_cdf(.975)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_train():
    split = pd.read_csv(ROOT / "results/01_data_audit/splits/split_assignments.csv", dtype=str)
    require(split.client_id.notna().all() and split.client_id.is_unique, "Invalid split IDs")
    ids = set(split.loc[split.split.eq("train"), "client_id"])
    features = pd.read_csv(
        ROOT / "results/02_customer_analysis/tables/customer_features.csv",
        dtype={"client_id": str},
        usecols=["client_id", "segment", *BALANCE],
    )
    labels = pd.read_csv(
        ROOT / "data/uplift_train.csv",
        dtype={"client_id": str},
        usecols=["client_id", "treatment_flg", "target"],
    )
    labels = labels[labels.client_id.isin(ids)]
    require(features.client_id.is_unique and set(features.client_id) == ids,
            "Customer features do not match the fixed training split")
    require(labels.client_id.is_unique and set(labels.client_id) == ids,
            "Training outcomes do not match the fixed training split")
    require(labels[["treatment_flg", "target"]].isin([0, 1]).all().all(), "Invalid training labels")
    require(set(features.segment) == set(SEGMENTS), "Unexpected customer segments")
    return features.merge(labels, on="client_id", validate="one_to_one")


def interval(estimate, se):
    require(se > 0, "Standard error must be positive")
    return {
        "difference_pp": 100 * estimate,
        "standard_error_pp": 100 * se,
        "ci_low_pp": 100 * (estimate - Z95 * se),
        "ci_high_pp": 100 * (estimate + Z95 * se),
        "p_value": erfc(abs(estimate / se) / sqrt(2)),
    }


def effect(frame, label):
    arms = frame.groupby("treatment_flg").target.agg(["size", "sum"]).reindex([0, 1])
    require(arms.notna().all().all(), f"Missing an arm in {label}")
    n0, n1 = (int(v) for v in arms["size"])
    y0, y1 = (int(v) for v in arms["sum"])
    require(min(y0, n0 - y0, y1, n1 - y1) >= 10, f"Insufficient cell count for normal CI: {label}")
    p0, p1 = y0 / n0, y1 / n1
    se = sqrt(p0 * (1 - p0) / n0 + p1 * (1 - p1) / n1)
    return {
        "segment": label, "control_n": n0, "sms_n": n1, "control_buyers": y0, "sms_buyers": y1,
        "control_rate": p0, "sms_rate": p1, **interval(p1 - p0, se),
    }


def holm(p_values):
    """Step-down adjustment, returned in the original order."""
    indexed = sorted(enumerate(p_values), key=lambda pair: pair[1])
    adjusted = [0.0] * len(indexed)
    previous = 0.0
    for rank, (idx, value) in enumerate(indexed):
        previous = max(previous, min(1.0, (len(indexed) - rank) * value))
        adjusted[idx] = previous
    return adjusted


def heterogeneity(segments):
    active = segments.loc["高价值活跃"]
    inactive = segments.loc["高价值待唤醒"]
    contrast = interval(
        (inactive.difference_pp - active.difference_pp) / 100,
        sqrt(inactive.standard_error_pp**2 + active.standard_error_pp**2) / 100,
    )
    weights = segments.standard_error_pp.pow(-2)
    common = (weights * segments.difference_pp).sum() / weights.sum()
    q = float((weights * (segments.difference_pp - common) ** 2).sum())
    # Five fixed groups give four degrees of freedom. This is the chi-square(4) survival function.
    require(len(segments) == 5, "Omnibus test expects five fixed segments")
    return {
        "high_value_contrast": {"comparison": "高价值待唤醒 − 高价值活跃", **contrast},
        "omnibus": {"q": q, "degrees_of_freedom": 4, "p_value": exp(-q / 2) * (1 + q / 2)},
    }


def balance_table(frame):
    covariates = frame[list(BALANCE)].copy()
    names = BALANCE.copy()
    for key in BALANCE:
        if covariates[key].isna().any():
            missing = f"{key}_missing"
            covariates[missing] = covariates[key].isna().astype(float)
            names[missing] = f"{BALANCE[key]}缺失"
    for i, segment in enumerate(SEGMENTS):
        key = f"segment_{i + 1}"
        covariates[key] = frame.segment.eq(segment).astype(float)
        names[key] = f"客群占比（{segment}）"
    control = covariates[frame.treatment_flg.eq(0)]
    sms = covariates[frame.treatment_flg.eq(1)]
    mean0, mean1 = control.mean(), sms.mean()
    sd = np.sqrt((control.var(ddof=1) + sms.var(ddof=1)) / 2)
    smd = (mean1 - mean0).div(sd.where(sd > 0))
    smd = smd.mask(sd.eq(0) & mean0.eq(mean1), 0)
    missing0, missing1 = control.isna().sum(), sms.isna().sum()
    return pd.DataFrame({
        "covariate": covariates.columns, "label": list(names.values()),
        "control_mean": mean0, "sms_mean": mean1, "control_missing": missing0,
        "sms_missing": missing1, "smd": smd, "absolute_smd": smd.abs(),
    }).sort_values("absolute_smd", ascending=False, na_position="first").reset_index(drop=True)


def p_text(p):
    return "<0.001" if p < .001 else f"{p:.3f}"


def write_report(path, overall, groups, balance, hte):
    top = balance.iloc[0]
    contrast = hte["high_value_contrast"]
    omnibus = hte["omnibus"]
    omnibus_p = "< 0.001" if omnibus["p_value"] < .001 else f"= {omnibus['p_value']:.3f}"
    n = overall["control_n"] + overall["sms_n"]
    interval_text = lambda r: f"[{r['ci_low_pp']:+.2f}, {r['ci_high_pp']:+.2f}]"
    contrast_result = (
        "区间跨零，证据不足以判定两群的增量不同。"
        if contrast["ci_low_pp"] <= 0 <= contrast["ci_high_pp"]
        else "区间未跨零，仍需在独立样本中验证差异的稳定性。"
    )
    text = [
        "# X5 短信营销实验分析", "",
        f"固定训练集 {n:,} 位客户中，短信组购买率为 {overall['sms_rate']:.2%}，对照组为 "
        f"{overall['control_rate']:.2%}。观察到的购买率差为 **{overall['difference_pp']:+.2f} 个百分点**"
        f"（95% CI {interval_text(overall)}）。", "",
        "## 样本与组间可比性", "",
        f"短信组 {overall['sms_n']:,} 人，对照组 {overall['control_n']:,} 人。通过客户编号将固定训练名单、"
        "第二阶段营销前特征和实验标签一对一关联。分群沿用第二阶段规则。",
        f"已检查的历史协变量中，绝对标准化均值差最大的是「{top.label}」"
        f"（|SMD| = {top.absolute_smd:.3f}）。0.10 仅作诊断参考。组间接近不能证明随机分配。", "",
        "## 总体与分群购买率差", "",
        "| 客群 | 对照组人数 | 短信组人数 | 对照组购买率 | 短信组购买率 | 差值（百分点） | 95% CI | Holm p |",
        "|---|---:|---:|---:|---:|---:|---|---:|",
        f"| 整体 | {overall['control_n']:,} | {overall['sms_n']:,} | {overall['control_rate']:.2%} | "
        f"{overall['sms_rate']:.2%} | {overall['difference_pp']:+.2f} | {interval_text(overall)} | — |",
    ]
    for segment, row in groups.iterrows():
        text.append(f"| {segment} | {int(row.control_n):,} | {int(row.sms_n):,} | {row.control_rate:.2%} | "
                    f"{row.sms_rate:.2%} | {row.difference_pp:+.2f} | {interval_text(row)} | {p_text(row.holm_p)} |")
    text += [
        "", "[查看购买率差与置信区间图](figures/sms_effect_forest.png)", "",
        "## 高价值客户是否值得优先召回", "",
        f"五群效果相同的联合检验得到 Q = {omnibus['q']:.2f}，df = 4，p {omnibus_p}。"
        "该检验只判断五群的差值是否存在总体差异。",
        f"高价值待唤醒组与高价值活跃组的购买率差再相减，得到 **{contrast['difference_pp']:+.2f} 个百分点**"
        f"（95% CI {interval_text(contrast)}，p = {p_text(contrast['p_value'])}）。{contrast_result}", "",
        "业务上，保留 RFM 分群作为后续策略比较的基线。高历史消费和高自然购买率都需要与短信增量分开评估。"
        "验证阶段可在相同的 30% 触达比例下比较 RFM 优先、随机排序和 Uplift 模型排序。触达成本和每笔增量购买毛利确认后，再评估利润。", "",
        "## 统计口径与边界", "",
        "- 购买率差等于短信组购买率减对照组购买率，两侧 95% 区间采用独立客户、非合并方差的正态近似。重点组间对比使用不重叠客群，合并两群差值的方差。",
        "- 五个群的组内检验用 Holm 校正，图与表的区间是逐项 95% 区间。五群联合检验使用逆方差加权的 Q 统计量。联合检验和重点组间对比单独报告。",
        "- SMD 为短信组与对照组均值差除以两组方差均值的平方根。缺失时按可用值比较均值，另查缺失比例。0.10 是筛查阈值。",
        "- 分析仅使用固定训练集。原划分按处理组与购买结果联合分层，目的是近似保留原样本比例。区间为训练样本的近似推断。",
        "- 将购买率差解释为短信因果效应，需要分配可交换性、触达定义和数据记录可靠等条件。项目资料尚未核实精确触达日期、结果窗口长度和随机分配协议。",
        "", "结果表与复现方法见 [本阶段索引](README.md)。", "",
    ]
    path.write_text("\n".join(text), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    tables = args.output / "tables"
    metadata = args.output / "metadata"
    tables.mkdir(parents=True, exist_ok=True)
    metadata.mkdir(parents=True, exist_ok=True)
    frame = load_train()
    overall = effect(frame, "整体")
    groups = pd.DataFrame([
        effect(frame.loc[frame.segment.eq(segment)], segment) for segment in SEGMENTS
    ]).set_index("segment")
    groups["holm_p"] = holm(groups.p_value)
    for key in ("control_n", "sms_n", "control_buyers", "sms_buyers"):
        require(groups[key].sum() == overall[key], f"Group totals differ from overall: {key}")
    balance = balance_table(frame)
    hte = heterogeneity(groups)
    results = pd.concat([pd.DataFrame([overall]), groups.reset_index()], ignore_index=True)
    results.to_csv(tables / "purchase_rate_effects.csv", index=False, encoding="utf-8-sig")
    balance.to_csv(tables / "covariate_balance.csv", index=False, encoding="utf-8-sig")
    summary = {
        "split": "train", "customers": len(frame), "overall": overall, **hte,
        "max_absolute_smd": float(balance.absolute_smd.max()),
        "checks": ["fixed_training_population", "one_to_one_join", "binary_treatment_and_outcome",
                   "segment_counts_and_buyers_reconcile", "sufficient_arm_counts"],
    }
    payload = json.dumps(summary, ensure_ascii=False, indent=2)
    (metadata / "experiment_summary.json").write_text(payload + "\n", encoding="utf-8")
    write_report(args.output / "短信营销实验分析报告.md", overall, groups, balance, hte)
    print(payload)


if __name__ == "__main__":
    main()
