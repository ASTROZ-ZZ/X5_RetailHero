#!/usr/bin/env python3
"""Render the two customer-analysis charts in a Power BI–inspired report style."""

import argparse
import csv
from functools import lru_cache
from math import ceil
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, to_rgb
from matplotlib.font_manager import FontProperties, findfont
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch, Patch, Rectangle
from matplotlib.ticker import MultipleLocator, PercentFormatter


ROOT = Path(__file__).resolve().parents[1]
INK = "#202E3B"
MUTED = "#526270"
GRID = "#E0E5E9"
WHITE = "#FFFFFF"
NAVY = "#183B5B"
STEEL = "#8198AB"
MISSING = "#F1F3F5"
COHORT_COLORS = LinearSegmentedColormap.from_list(
    "cohort_blues", ["#EEF3F7", "#A2B6C7", NAVY]
)


@lru_cache
def font(kind="cn", size=11, bold=False):
    if kind == "cn":
        families = ["SimHei", "STHeiti", "Heiti SC", "Heiti TC"]
        filenames = ["C:/Windows/Fonts/simhei.ttf", "/System/Library/Fonts/STHeiti Medium.ttc"]
    else:
        families = ["Times New Roman"]
        mac_file = "Times New Roman Bold.ttf" if bold else "Times New Roman.ttf"
        win_file = "timesbd.ttf" if bold else "times.ttf"
        filenames = [f"/System/Library/Fonts/Supplemental/{mac_file}", f"C:/Windows/Fonts/{win_file}"]
    for filename in filenames:
        if Path(filename).is_file():
            return FontProperties(fname=filename, size=size)
    for family in families:
        try:
            file = findfont(FontProperties(family=family, weight="bold" if bold else "normal"),
                            fallback_to_default=False)
        except ValueError:
            continue
        return FontProperties(fname=file, size=size)
    raise RuntimeError(f"Install one of the required chart fonts: {', '.join(families)}")


def load(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def panel(title, subtitle):
    fig = plt.figure(figsize=(9.6, 5.0), facecolor=WHITE)
    fig.add_artist(FancyBboxPatch(
        (0.025, 0.04), 0.95, 0.92, transform=fig.transFigure,
        boxstyle="round,pad=0.005,rounding_size=0.018",
        facecolor=WHITE, edgecolor=GRID, linewidth=0.8, zorder=-1,
    ))
    fig.text(0.065, 0.878, title, fontproperties=font(size=23), color=INK, va="center")
    fig.text(0.066, 0.810, subtitle, fontproperties=font(size=10.5), color=MUTED, va="center")
    fig.add_artist(Line2D([0.065, 0.935], [0.755, 0.755], transform=fig.transFigure,
                          color=GRID, linewidth=0.8))
    return fig


def segment_chart(rows, path):
    fig = panel("客群人数与消费贡献", "按最近购买时间、购买频次和消费金额分群")
    ax = fig.add_axes([0.193, 0.198, 0.697, 0.454], facecolor=WHITE)
    positions = list(range(len(rows)))
    series = [
        ("customer_share", -0.17, STEEL, "客户人数占比"),
        ("sales_share", 0.17, NAVY, "历史消费金额占比"),
    ]
    xmax = max(0.4, ceil(max(float(r[k]) for r in rows for k, *_ in series) * 10) / 10)
    for key, offset, color, _ in series:
        shares = [float(row[key]) for row in rows]
        marks = ax.barh([p + offset for p in positions], shares, height=0.27,
                        color=color, edgecolor="none", zorder=3)
        ax.bar_label(marks, labels=[f"{v:.1%}" for v in shares], padding=5,
                     color=INK, fontproperties=font("en", 11, True))

    ax.set_yticks(positions, [r["segment"] for r in rows], fontproperties=font(size=11.5))
    ax.invert_yaxis()
    ax.set_xlim(0, xmax + 0.027)
    ax.xaxis.set_major_locator(MultipleLocator(0.1))
    ax.xaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    for label in ax.get_xticklabels():
        label.set_fontproperties(font("en", 10.5))
    ax.tick_params(axis="y", length=0, pad=10, labelcolor=INK)
    ax.tick_params(axis="x", length=0, pad=8, labelcolor=MUTED)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.axvline(0, color="#BAC4CC", linewidth=0.8, zorder=2)
    fig.legend(
        handles=[Patch(facecolor=color, edgecolor="none", label=label) for _, _, color, label in series],
        loc="upper left", bbox_to_anchor=(0.183, 0.723), ncols=2, frameon=False,
        prop=font(size=10.5), labelcolor=INK, columnspacing=2.0, handlelength=1.3,
    )
    fig.text(0.065, 0.094, "分析范围：固定训练集", fontproperties=font(size=9), color=MUTED)
    fig.savefig(path, dpi=200, facecolor=fig.get_facecolor())
    plt.close(fig)


def data_text_color(background):
    channels = to_rgb(background)
    linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in channels]
    luminance = sum(value * weight for value, weight in zip(linear, (.2126, .7152, .0722)))
    return WHITE if 1.05 / (luminance + .05) >= 4.5 else INK


def cohort_chart(rows, path):
    fig = panel("按首次观察购买月分组的复购矩阵", "每格显示该组客户在对应月份至少购买一次的比例")
    cohorts = sorted({r["cohort_month"] for r in rows})
    offsets = sorted({int(r["month_offset"]) for r in rows})
    lookup = {(r["cohort_month"], int(r["month_offset"])): r for r in rows}
    ax = fig.add_axes([0.065, 0.185, 0.870, 0.526])
    left, count_width = 1.18, 0.77
    start = left + count_width
    width = (6.6 - start) / len(offsets)
    ax.set_xlim(0, 6.6)
    ax.set_ylim(len(cohorts) + 0.9, 0)
    ax.axis("off")
    ax.add_patch(Rectangle((0, 0), 6.6, .90, facecolor="#EBEFF3", edgecolor="none"))
    ax.text(.115, .45, "首次观察购买月", fontproperties=font(size=10.5), color=INK, va="center")
    ax.text(left + count_width - .15, .45, "客户数", fontproperties=font(size=10.5),
            color=INK, va="center", ha="right")
    for j, offset in enumerate(offsets):
        ax.text(start + (j + .5) * width, .45, f"M{offset}",
                fontproperties=font("en", 12, True), color=INK, va="center", ha="center")
    for i, cohort in enumerate(cohorts):
        y = i + .90
        ax.add_patch(Rectangle((0, y), start, 1, facecolor=WHITE if i % 2 == 0 else "#F7F8FA",
                               edgecolor=WHITE, linewidth=1))
        ax.text(.115, y + .5, cohort, fontproperties=font("en", 12, True), color=INK, va="center")
        ax.text(left + count_width - .15, y + .5, f"{int(lookup[cohort, 0]['cohort_customers']):,}",
                fontproperties=font("en", 12), color=INK, va="center", ha="right")
        for j, offset in enumerate(offsets):
            value = lookup[cohort, offset]["repeat_rate"]
            rate = float(value) if value else None
            fill = MISSING if rate is None else COHORT_COLORS(rate)
            x = start + j * width
            ax.add_patch(Rectangle((x, y), width, 1, facecolor=fill, edgecolor=WHITE, linewidth=1.6))
            label = "—" if rate is None else f"{rate:.1%}"
            color = MUTED if rate is None else data_text_color(fill)
            ax.text(x + width / 2, y + .5, label, fontproperties=font("en", 13, rate is not None),
                    color=color, ha="center", va="center")
    fig.text(.065, .119, "M0", fontproperties=font("en", 10, True), color=MUTED)
    fig.text(.090, .119, "为分组当月。破折号表示分组月或观察月不完整，或超出观察窗口。",
             fontproperties=font(size=9.5), color=MUTED)
    fig.savefig(path, dpi=200, facecolor=fig.get_facecolor())
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "results/02_customer_analysis")
    args = parser.parse_args()
    figures = args.output / "figures"
    figures.mkdir(exist_ok=True)
    segment_chart(load(args.output / "tables/segment_summary.csv"), figures / "rfm_segment_share.png")
    cohort_chart(load(args.output / "tables/cohort_repeat.csv"), figures / "cohort_purchase_activity.png")


if __name__ == "__main__":
    main()
