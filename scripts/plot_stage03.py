#!/usr/bin/env python3
"""Render the SMS experiment forest plot using the X5 report style."""

import argparse
from math import ceil, floor
from pathlib import Path

from plot_stage02 import GRID, INK, MUTED, NAVY, STEEL, WHITE, font, load, panel, plt
from matplotlib.ticker import MultipleLocator


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "results/03_sms_experiment")
    args = parser.parse_args()
    rows = load(args.output / "tables/purchase_rate_effects.csv")
    figures = args.output / "figures"
    figures.mkdir(exist_ok=True)
    fig = panel("短信组与对照组的购买率差", "整体与五个客群的估计值和置信区间")
    ax = fig.add_axes([.227, .225, .45, .461], facecolor=WHITE)
    ax.axvline(0, color="#8695A2", linewidth=1, linestyle="--")
    ax.xaxis.set_major_locator(MultipleLocator(2))
    ax.grid(axis="x", color=GRID, linewidth=.8)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_visible(False)

    lo = min(float(row["ci_low_pp"]) for row in rows)
    hi = max(float(row["ci_high_pp"]) for row in rows)
    ax.set_xlim(min(-2, floor(lo)), max(2, ceil(hi)) + .30)
    ax.set_ylim(len(rows) - .52, -.58)
    ax.set_yticks([])
    ax.tick_params(axis="x", length=0, pad=8, labelcolor=MUTED)
    for label in ax.get_xticklabels():
        label.set_fontproperties(font("en", 10.5))
    ax.text(1.02, -.16, "百分点", transform=ax.transAxes, ha="left",
            fontproperties=font(size=9.5), color=MUTED)

    labels = fig.add_axes([.065, .225, .86, .461], frameon=False)
    labels.set(xlim=(0, 1), ylim=ax.get_ylim())
    labels.axis("off")
    labels.text(0, -.91, "客群", fontproperties=font(size=10), color=MUTED)
    labels.text(.76, -.91, "差值及区间", fontproperties=font(size=10), color=MUTED)
    for i, row in enumerate(rows):
        left, point, right = (float(row[k]) for k in ("ci_low_pp", "difference_pp", "ci_high_pp"))
        color = NAVY if i == 0 else STEEL
        ax.hlines(i, left, right, color=color, linewidth=1.9)
        ax.vlines([left, right], i - .08, i + .08, color=color, linewidth=1.3)
        ax.scatter(point, i, s=49 if i == 0 else 29, marker="D" if i == 0 else "o",
                   color=color, zorder=3)
        labels.text(0, i, row["segment"], va="center", fontproperties=font(size=11.5), color=INK)
        labels.text(.76, i, f"{point:+.2f}  [{left:+.2f}, {right:+.2f}]", va="center",
                    fontproperties=font("en", 11, i == 0), color=INK)
    fig.text(.065, .097, "95% CI", fontproperties=font("en", 10, True), color=MUTED)
    fig.text(.116, .097, "为逐项置信区间。虚线为零差值。分析范围为固定训练集。",
             fontproperties=font(size=9.5), color=MUTED)
    fig.savefig(figures / "sms_effect_forest.png", dpi=200, facecolor=WHITE)
    plt.close(fig)


if __name__ == "__main__":
    main()
