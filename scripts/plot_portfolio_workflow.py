#!/usr/bin/env python3
"""Create the portrait X5 workflow diagram for portfolio and print use."""

import argparse
from pathlib import Path

from matplotlib.patches import FancyArrowPatch, Rectangle
from plot_stage02 import GRID, INK, MUTED, NAVY, STEEL, WHITE, font, plt

ROOT = Path(__file__).resolve().parents[1]
LIGHT = "#EDF3F7"

STAGES = [
    ("01", "数据审计与固定划分", "核对六张 CSV 的字段、键、时间和关联覆盖。",
     "按客户与交易编号锁定订单粒度，冻结训练、验证和保留集。"),
    ("02", "客户消费分析", "汇总训练客户的历史订单、消费、品类和购买日期。",
     "产出 RFM、复购间隔、月度 cohort 与客户特征表。"),
    ("03", "短信实验分析", "在训练集内比较短信组与对照组，估计总体和五群购买率差。",
     "检查组间平衡，并检验两类高价值客户的差异。"),
    ("04", "候选策略与验证集比较", "基于训练集构建六种排序策略，在同一验证集比前 30%。",
     "选出 T-Learner 逻辑回归，并锁定模型、对照和触达比例。"),
    ("05", "最终保留集独立评估", "锁定模型给 40,009 人打分，每条策略选前 12,002 人。",
     "复算配对区间，依据两条对照的领先下界判断是否采用。"),
    ("06", "离线预测交付", "锁定配置用全部 200,039 位有标签客户重训。",
     "给 200,123 位官方测试客户打分，核验格式、顺序与覆盖。"),
    ("07", "优化诊断与模型保留", "只用训练与验证客户做三次重复五折，比较两项新行为特征。",
     "新增特征均值改善约 0.02 个百分点，离线交付沿用原模型。"),
]
GATES = [
    (0, "固定样本边界", ("训练 120,022 人", "验证 40,008 人", "保留 40,009 人")),
    (3, "锁定策略", ("前 30% 触达", "随机排序与 RFM 对照", "冻结特征、模型与规则")),
    (4, "业务判断", ("优于 RFM", "相对随机的区间跨零", "未达到采用门槛")),
    (5, "交付边界", ("官方测试集没有标签", "核验预测文件完整性")),
]


def render(path):
    fig = plt.figure(figsize=(10.5, 12.6), facecolor=WHITE)

    def write(x, y, value, size=10, color=INK, latin=False, bold=False, align="left"):
        fig.text(x, y, value, color=color, fontproperties=font("en" if latin else "cn", size, bold),
                 ha=align, va="center")

    def box(x, y, w, h, fill, stroke="none"):
        fig.add_artist(Rectangle((x,y),w,h,facecolor=fill,edgecolor=stroke,
                                 linewidth=.7,transform=fig.transFigure,zorder=0))

    def arrow(start, end, color=STEEL):
        fig.add_artist(FancyArrowPatch(start,end,transform=fig.transFigure,arrowstyle="-|>",
                                       mutation_scale=9,linewidth=.9,color=color))

    write(.065,.945,"短信营销研究的完整流程",24,NAVY)
    write(.066,.908,"X5 RetailHero",12,NAVY,latin=True,bold=True)
    write(.183,.908,"从订单归并到触达策略验证",11,MUTED)
    box(.065,.877,.87,.001,GRID)
    write(.065,.850,"研究步骤与产出",11,MUTED)
    write(.763,.850,"关键检查点",11,MUTED)

    x, w, h, top, stride = .065,.646,.096,.823,.109
    for i,(number,title,detail,output) in enumerate(STAGES):
        y=top-i*stride-h
        box(x,y,w,h,WHITE,GRID)
        box(x,y,.065,h,LIGHT)
        write(x+.033,y+h/2,number,18,NAVY,latin=True,bold=True,align="center")
        write(x+.085,y+h*.75,title,13,NAVY)
        write(x+.085,y+h*.46,detail,9.6)
        write(x+.085,y+h*.20,output,9.6,MUTED)
        if i<len(STAGES)-1:
            arrow((x+.033,y-.001),(x+.033,y-.012))

    for stage,title,notes in GATES:
        y=top-stage*stride-h
        box(.756,y,.179,h,LIGHT)
        arrow((x+w+.002,y+h/2),(.752,y+h/2))
        write(.768,y+h*.76,title,10.8,NAVY)
        for j,note in enumerate(notes):
            write(.768,y+h*(.50-j*.186),note,9.15)
    for stage,value,label in [
        (1,"37.3%","高价值客群消费贡献"),
        (2,"+3.32","整体购买率差（百分点）"),
        (6,"+0.02","特征改进均值（百分点）"),
    ]:
        y=top-stage*stride-h
        box(.775,y+h*.17,.001,h*.66,GRID)
        write(.790,y+h*.64,value,17,NAVY,latin=True,bold=True)
        write(.790,y+h*.28,label,8.8,MUTED)
    box(.065,.054,.87,.001,GRID)
    write(.065,.032,"业务验证以最终保留集为准。真实投放需在新样本上按相同预算直接比较两种选人策略。",9.5,MUTED)
    path.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(path,dpi=260,facecolor=WHITE)
    plt.close(fig)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=ROOT/"results/portfolio/X5_RetailHero_研究流程图.png")
    render(parser.parse_args().output)


if __name__ == "__main__":
    main()
