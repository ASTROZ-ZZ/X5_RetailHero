#!/usr/bin/env python3
"""Render a shareable one-page X5 case study from verified project results."""

import argparse
import json
from pathlib import Path

from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from matplotlib.ticker import MultipleLocator, PercentFormatter

from plot_stage02 import GRID, INK, MUTED, NAVY, STEEL, WHITE, font, load, plt


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
LIGHT = "#F1F5F8"


def read_meta(stage, name):
    return json.loads((RESULTS / stage / "metadata" / f"{name}.json").read_text())


def line(fig, x1, x2, y, color=GRID):
    fig.add_artist(Line2D([x1, x2], [y, y], transform=fig.transFigure, color=color, lw=.8))


def write(fig, x, y, text, size, color=INK, english=False, bold=False, align="left"):
    fig.text(x, y, text, fontproperties=font("en" if english else "cn", size, bold),
             color=color, ha=align, va="center")


def make_portfolio(output):
    audit = read_meta("01_data_audit", "audit_summary")
    experiment = read_meta("03_sms_experiment", "experiment_summary")["overall"]
    delivery = read_meta("06_offline_delivery", "submission_summary")
    holdout = read_meta("05_holdout_evaluation", "evaluation_summary")
    optimization = read_meta("07_uplift_optimization", "cv_summary")
    segment = load(RESULTS / "02_customer_analysis/tables/segment_summary.csv")
    validation = load(RESULTS / "04_uplift_baselines/tables/candidate_vs_baselines.csv")
    held = load(RESULTS / "05_holdout_evaluation/tables/holdout_candidate_vs_baselines.csv")
    high_value = [r for r in segment if r["segment"] in ("高价值活跃", "高价值待唤醒")]
    share = [sum(float(r[field]) for r in high_value) for field in ("customer_share", "sales_share")]
    comparisons = [
        next(r for r in validation if r["comparator"] == "random"),
        next(r for r in held if r["comparator"] == "random"),
        next(r for r in held if r["comparator"] == "rfm"),
    ]
    if any(r["policy"] != holdout["candidate"] for r in comparisons):
        raise ValueError("Strategy comparison does not match the locked candidate")
    purchase_rows = next(r["rows"] for r in audit["files"] if r["table"] == "purchases")
    sample_sizes = [purchase_rows, delivery["labeled_customers"], delivery["scored_customers"]]

    fig = plt.figure(figsize=(11.6, 8.25), facecolor=WHITE)
    write(fig, .065, .943, "短信营销中，模型选人优于随机吗？", 26)
    write(fig, .066, .895, "X5 RetailHero", 13, NAVY, english=True, bold=True)
    write(fig, .172, .895, "公开竞赛数据的离线复现", 11, MUTED)

    fig.add_artist(Rectangle((.065, .754), .87, .107, transform=fig.transFigure,
                             facecolor=LIGHT, edgecolor="none", zorder=-1))
    for center, number, label in zip((.208,.5,.792), sample_sizes,
                                     ("历史商品明细", "有标签客户", "官方测试预测")):
        write(fig, center, .819, f"{number:,}", 23, NAVY, english=True, bold=True, align="center")
        write(fig, center, .780, label, 10.5, MUTED, align="center")
    line(fig, .065, .935, .722)

    write(fig, .065, .686, "高价值客户的消费贡献", 15)
    write(fig, .066, .653, "以训练客户历史订单和消费金额分层", 10, MUTED)
    ax = fig.add_axes([.17, .502, .25, .127], facecolor=WHITE)
    ax.barh([0,1], share, color=[STEEL, NAVY], height=.42, edgecolor="none", zorder=3)
    ax.set_yticks([0,1], ["人数占比", "消费额占比"], fontproperties=font(size=10))
    ax.invert_yaxis()
    ax.set_xlim(0,.45)
    ax.xaxis.set_major_locator(MultipleLocator(.1))
    ax.xaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    ax.tick_params(length=0, labelcolor=MUTED, pad=5)
    ax.grid(axis="x", color=GRID)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_visible(False)
    for label in ax.get_xticklabels():
        label.set_fontproperties(font("en", 9.5))
    for y, v in enumerate(share):
        ax.annotate(f"{v:.1%}", (v,y), xytext=(5,0), textcoords="offset points",
                    va="center", color=INK, fontproperties=font("en", 11, True))

    write(fig, .525, .686, "短信组整体购买率更高", 15)
    write(fig, .526, .653, "固定训练集的短信实验", 10, MUTED)
    for x, key, label in [( .590, "control_rate","对照组购买率"), (.813,"sms_rate","短信组购买率")]:
        write(fig, x, .581, f"{experiment[key]:.2%}", 22, NAVY, english=True, bold=True, align="center")
        write(fig, x, .549, label, 9.5, MUTED, align="center")
    write(fig, .526, .510, "购买率差", 10.5, INK)
    write(fig, .624, .510, f"{experiment['difference_pp']:+.2f}", 12.5, NAVY, english=True, bold=True)
    write(fig, .681, .510, "个百分点", 10, INK)
    write(fig, .763, .510, f"95% CI [{experiment['ci_low_pp']:+.2f}, {experiment['ci_high_pp']:+.2f}]",
          10.5, MUTED, english=True)

    line(fig, .065, .935, .461)
    write(fig, .065, .427, "相同触达预算下，模型相对基线的领先幅度", 15)
    write(fig, .066, .397, "T-Learner", 10.5, MUTED, english=True, bold=True)
    write(fig, .145, .397, "逻辑回归。各策略均选择前百分之三十客户，横线为配对区间。", 10, MUTED)
    rows_ax = fig.add_axes([.296, .211, .408, .157], facecolor=WHITE)
    rows_ax.set(xlim=(-2.2,6), ylim=(2.5,-.5), yticks=[])
    rows_ax.xaxis.set_major_locator(MultipleLocator(2))
    rows_ax.tick_params(length=0, pad=5, labelcolor=MUTED)
    rows_ax.grid(axis="x", color=GRID)
    rows_ax.set_axisbelow(True)
    rows_ax.axvline(0,lw=.9,ls="--",color=MUTED)
    for spine in rows_ax.spines.values():
        spine.set_visible(False)
    for tick in rows_ax.get_xticklabels():
        tick.set_fontproperties(font("en", 9.5))
    titles = ["验证集，相对随机", "保留集，相对随机", "保留集，相对"]
    for i,(row,title) in enumerate(zip(comparisons,titles)):
        point,lo,hi = (float(row[k]) for k in ("difference_pp","ci_low_pp","ci_high_pp"))
        color = NAVY if i == 1 else STEEL
        rows_ax.hlines(i,lo,hi,color=color,lw=1.8)
        rows_ax.vlines([lo,hi],i-.10,i+.10,color=color,lw=1.2)
        rows_ax.scatter(point,i,color=color,s=42 if i==1 else 31,marker="D" if i==1 else "o",zorder=4)
        yp = .211 + .157 * (2.5-i) / 3
        write(fig,.065,yp,title,11,NAVY if i==1 else INK)
        if i==2:
            write(fig,.151,yp,"RFM",11,INK,english=True)
        write(fig,.754,yp,f"{point:+.2f}   [{lo:+.2f}, {hi:+.2f}]",12,
              NAVY if i==1 else INK,english=True,bold=i==1)
    write(fig,.754,.368,"百分点",9.5,MUTED)
    write(fig,.821,.368,"95% CI",10,MUTED,english=True)

    delta = optimization["model_results"]["behavior_t"]["mean_vs_base_t_pp"]
    fig.add_artist(Rectangle((.065,.064),.87,.096,transform=fig.transFigure,facecolor=LIGHT,edgecolor="none",zorder=-1))
    write(fig,.083,.127,"保留集上优于历史分层规则，未确认优于随机排序。",13,NAVY)
    write(fig,.083,.090,"购买节奏特征在重复验证中的平均改善仅",10,MUTED)
    write(fig,.307,.090,f"{delta:+.2f}",11,MUTED,english=True,bold=True)
    write(fig,.350,.090,"个百分点，离线交付沿用原模型。",10,MUTED)

    write(fig,.066,.037,"数据来源：公开竞赛历史数据。官方测试集用于离线打分。",8.5,MUTED)
    output.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(output,dpi=240,facecolor=WHITE)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=RESULTS / "portfolio/X5_RetailHero_项目一页图.png")
    make_portfolio(parser.parse_args().output)


if __name__ == "__main__":
    main()
