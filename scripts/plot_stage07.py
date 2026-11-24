#!/usr/bin/env python3
"""Show the repeat means behind the development-set uplift diagnosis."""

import argparse
from collections import defaultdict
from pathlib import Path

from plot_stage02 import GRID, INK, MUTED, NAVY, STEEL, WHITE, font, panel, plt, load
from matplotlib.lines import Line2D


ROOT = Path(__file__).resolve().parents[1]
NAMES = {
    "base_t": "原双模型逻辑回归",
    "behavior_t": "双模型加行为特征",
    "interaction_s": "正则化单模型加行为特征",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "results/07_uplift_optimization")
    out = parser.parse_args().output
    figs = out / "figures"
    figs.mkdir(exist_ok=True)
    repeats = defaultdict(list)
    for row in load(out / "tables/repeat_summary.csv"):
        repeats[row["model"]].append(float(row["vs_random_pp"]))
    summary = load(out / "tables/model_summary.csv")
    fig = panel("三种方案的重复验证表现", "同一触达比例下相对随机排序的购买率差")
    ax = fig.add_axes([.305, .24, .54, .43], facecolor=WHITE)
    ax.set_ylim(len(summary) - .5, -.5)
    ax.set_yticks(range(len(summary)), [NAMES[r["model"]] for r in summary], fontproperties=font(size=11))
    ax.set_xlim(min(0, min(min(v) for v in repeats.values())-.2), max(max(v) for v in repeats.values())+.5)
    ax.axvline(0, color="#8695A2", linestyle="--", linewidth=1)
    ax.grid(axis="x", color=GRID)
    ax.tick_params(length=0, pad=8, labelcolor=INK)
    for spine in ax.spines.values():
        spine.set_visible(False)
    for label in ax.get_xticklabels():
        label.set_fontproperties(font("en", 10.5))
    for i, row in enumerate(summary):
        values = repeats[row["model"]]
        average = float(row["mean_vs_random_pp"])
        ax.hlines(i, min(values), max(values), color=GRID, linewidth=2)
        ax.scatter(values, [i+.04+j*.13 for j in range(len(values))], color=STEEL, s=38, zorder=3)
        ax.scatter(average, i-.08, color=NAVY, marker="D", s=58, zorder=4)
        ax.annotate(f"{average:+.2f}", (average, i-.08), xytext=(8, 0), textcoords="offset points",
                    fontsize=11, fontproperties=font("en", 11, True), va="center", color=INK)
    fig.legend(handles=[
        Line2D([], [], color=NAVY, marker="D", linestyle="", label="全部折均值"),
        Line2D([], [], color=STEEL, marker="o", linestyle="", label="单次重复的五折均值"),
    ], loc="upper left", bbox_to_anchor=(.292, .735), frameon=False, ncols=2, prop=font(size=10))
    fig.text(.065, .10, "横轴单位为百分点。各次重复使用同一批开发客户。",
             fontproperties=font(size=9.5), color=MUTED)
    fig.savefig(figs / "repeated_cv_uplift.png", dpi=200, facecolor=WHITE)
    plt.close(fig)


if __name__ == "__main__":
    main()
