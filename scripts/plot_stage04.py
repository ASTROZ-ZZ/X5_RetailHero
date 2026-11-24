#!/usr/bin/env python3
"""Render a policy comparison for the validation split."""

import argparse
from math import ceil, floor
from pathlib import Path

from plot_stage02 import GRID, INK, MUTED, NAVY, STEEL, WHITE, font, load, panel, plt
from matplotlib.ticker import MultipleLocator


ROOT = Path(__file__).resolve().parents[1]
NAMES = {
    "random": "随机排序",
    "rfm": "RFM 规则",
    "purchase_probability": "普通购买概率",
    "s_logistic": "单模型逻辑回归",
    "t_logistic": "双模型逻辑回归",
    "t_hist_gradient": "双模型梯度提升树",
}


def plot_top30(rows, path, sample="验证集"):
    fig = panel("同样触达比例下的策略比较", f"{sample}前百分之三十客户的短信组与对照组购买率差")
    ax = fig.add_axes([.25, .23, .44, .48], facecolor=WHITE)
    labels = fig.add_axes([.065, .23, .87, .48], frameon=False)
    lo = min(float(row["ci_low_pp"]) for row in rows)
    hi = max(float(row["ci_high_pp"]) for row in rows)
    ax.set(xlim=(min(0, floor(lo)), ceil(hi)), ylim=(len(rows)-.55, -.55), yticks=[])
    labels.set(xlim=(0, 1), ylim=ax.get_ylim())
    labels.axis("off")
    ax.axvline(0, color="#8695A2", linewidth=1, linestyle="--")
    ax.xaxis.set_major_locator(MultipleLocator(2))
    ax.grid(axis="x", color=GRID, linewidth=.8)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(axis="x", length=0, pad=8, labelcolor=MUTED)
    for label in ax.get_xticklabels():
        label.set_fontproperties(font("en", 10.5))
    for i, row in enumerate(rows):
        low, estimate, high = (float(row[k]) for k in ("ci_low_pp", "uplift_pp", "ci_high_pp"))
        color = NAVY if i == 0 else STEEL
        ax.hlines(i, low, high, color=color, linewidth=1.9)
        ax.vlines([low, high], i-.08, i+.08, color=color, linewidth=1.3)
        ax.scatter(estimate, i, s=49 if i == 0 else 29, marker="D" if i == 0 else "o",
                   color=color, zorder=3)
        name = NAMES[row["policy"]]
        if row["policy"] == "rfm":
            labels.text(0, i, "RFM", va="center", fontproperties=font("en", 11.5), color=INK)
            labels.text(.045, i, "规则", va="center", fontproperties=font(size=11.5), color=INK)
        else:
            labels.text(0, i, name, va="center", fontproperties=font(size=11.5), color=INK)
        labels.text(.755, i, f"{estimate:+.2f}  [{low:+.2f}, {high:+.2f}]",
                    va="center", fontproperties=font("en", 11, i == 0), color=INK)
    fig.text(.065, .099, "95% CI", fontproperties=font("en", 10, True), color=MUTED)
    fig.text(.116, .099, "为逐项置信区间。横轴单位为百分点。",
             fontproperties=font(size=9.5), color=MUTED)
    fig.savefig(path, dpi=200, facecolor=WHITE)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "results/04_uplift_baselines")
    args = parser.parse_args()
    figures = args.output / "figures"
    figures.mkdir(exist_ok=True)
    plot_top30(load(args.output / "tables/validation_at30.csv"), figures / "validation_uplift.png")


if __name__ == "__main__":
    main()
