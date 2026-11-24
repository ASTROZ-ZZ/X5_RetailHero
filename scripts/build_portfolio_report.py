#!/usr/bin/env python3
"""Build a landscape X5 portfolio case study from the saved analysis artifacts."""

import argparse
import csv
from html import escape
import json
from pathlib import Path
import re

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
DEST = RESULTS / "portfolio/X5_RetailHero_作品集报告.pdf"
W, H = landscape(A4)
M = 44
LEFT, RIGHT, COL = M, 441, 356
WIDTH = W - 2*M
NAVY, INK, MUTED = map(HexColor, ("#183B5B", "#202E3B", "#526270"))
GRID, PALE, WARM = map(HexColor, ("#DBE3EB", "#EDF3F7", "#A56A43"))
DARK = HexColor("#102A42")
CJK = "Heiti"
LATIN = "TimesNewRoman"
BOLD = "TimesNewRomanBold"
STAGES = {
    "audit": "01_data_audit", "customer": "02_customer_analysis",
    "experiment": "03_sms_experiment", "validation": "04_uplift_baselines",
    "holdout": "05_holdout_evaluation", "delivery": "06_offline_delivery",
    "optimize": "07_uplift_optimization",
}


def setup_fonts():
    candidates = {
        CJK: ["/System/Library/Fonts/STHeiti Medium.ttc", "C:/Windows/Fonts/simhei.ttf"],
        LATIN: ["/System/Library/Fonts/Supplemental/Times New Roman.ttf", "C:/Windows/Fonts/times.ttf"],
        BOLD: ["/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf", "C:/Windows/Fonts/timesbd.ttf"],
    }
    for alias, choices in candidates.items():
        path = next((p for p in choices if Path(p).is_file()), None)
        if not path:
            raise RuntimeError(f"Required portfolio font missing: {alias}")
        pdfmetrics.registerFont(TTFont(alias, path))


def artifact(stage, path):
    return RESULTS / STAGES[stage] / path


def data(stage, path):
    return json.loads(artifact(stage, path).read_text(encoding="utf-8"))


def rows(stage, path):
    with artifact(stage, path).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def m(value):
    return f"{int(value):,}"


def p(value):
    return f"{float(value):.2%}"


def pp(value):
    return f"{float(value):+.2f}"


def ci(row):
    return f"[{pp(row['ci_low_pp'])}, {pp(row['ci_high_pp'])}]"


def markup(text, bold=False):
    parts = re.split(r"([A-Za-z0-9][A-Za-z0-9 .,+%/_:@=\-\[\]()]*|[+\-][0-9][0-9.,%]*)", str(text))
    return "".join(
        f'<font name="{BOLD if bold else LATIN}">{escape(part)}</font>' if i%2 else escape(part)
        for i, part in enumerate(parts)
    )


def paragraph(text, size, color, bold=False):
    return Paragraph(markup(text,bold), ParagraphStyle(
        "p", fontName=CJK, fontSize=size, leading=size*1.52, wordWrap="CJK", textColor=color
    ))


def put(c, text, x, y, width=COL, size=10.4, color=INK, gap=7, bold=False):
    para = paragraph(text,size,color,bold)
    _, height = para.wrap(width,H)
    if y-height < 42:
        raise ValueError(f"Text below the page grid on page {c.getPageNumber()}: {text[:35]}")
    para.drawOn(c,x,y-height)
    return y-height-gap


def note(c, body, x, y, w=COL):
    para = paragraph(body,10,NAVY)
    _, height = para.wrap(w-24,H)
    floor = y-height-20
    if floor < 42:
        raise ValueError(f"Note below page grid on page {c.getPageNumber()}")
    c.setFillColor(PALE)
    c.rect(x,floor,w,height+20,stroke=0,fill=1)
    para.drawOn(c,x+12,floor+10)
    return floor-13


def heading(c, title, x, y, w=COL):
    return put(c,title,x,y,w,13,NAVY,gap=4,bold=True)


def table(c, headers, records, widths, x, y, size=9.1):
    cells = [[paragraph(col,size,white,True) for col in headers]]
    cells += [[paragraph(col,size,INK) for col in row] for row in records]
    t = Table(cells, colWidths=widths)
    t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),NAVY),("ROWBACKGROUNDS",(0,1),(-1,-1),[white,PALE]),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),("TOPPADDING",(0,0),(-1,-1),5),
        ("BOTTOMPADDING",(0,0),(-1,-1),5),("LEFTPADDING",(0,0),(-1,-1),8),
        ("RIGHTPADDING",(0,0),(-1,-1),6),("LINEBELOW",(0,-1),(-1,-1),.55,GRID),
    ]))
    _, ht = t.wrap(sum(widths),H)
    if y-ht < 42:
        raise ValueError(f"Table below page grid on page {c.getPageNumber()}")
    t.drawOn(c,x,y-ht)
    return y-ht-12


def image(c, filename, x, y, width, label, max_height=380):
    asset = ImageReader(str(filename))
    iw,ih = asset.getSize()
    h = min(width * ih / iw, max_height)
    w = h * iw / ih
    if y-h < 58:
        raise ValueError(f"Figure below page grid on page {c.getPageNumber()}")
    c.drawImage(asset,x+(width-w)/2,y-h,width=w,height=h,mask="auto")
    return put(c,label,x,y-h-5,width,8.5,MUTED,7)


def coverage_curve(c, x, y, width):
    series = rows("validation", "tables/validation_curves.csv")
    keep = {"t_logistic": ("T-Learner", NAVY), "random": ("随机", MUTED), "rfm": ("RFM", WARM)}
    plot_left, plot_bottom, plot_width, plot_height = x+25, y-143, width-37, 112
    bound = max(8, 2 * int((max(abs(float(r["uplift_pp"])) for r in series if r["policy"] in keep) + 1.99) / 2))
    floor = min(0, 2 * int(min(float(r["uplift_pp"]) for r in series if r["policy"] in keep) // 2))
    px = lambda coverage: plot_left + plot_width * coverage / 100
    py = lambda effect: plot_bottom + plot_height * (effect-floor)/(bound-floor)
    j=0
    for _, (symbol, color) in keep.items():
        cx=x+25+j*106
        c.setStrokeColor(color)
        c.setLineWidth(2)
        c.line(cx,y-12,cx+14,y-12)
        put(c,symbol,cx+19,y-4,79,9,MUTED)
        j+=1
    c.setFont(LATIN,8)
    c.setFillColor(MUTED)
    c.setLineWidth(.5)
    c.setStrokeColor(GRID)
    for t in range(floor,bound+1,2):
        c.line(plot_left,py(t),plot_left+plot_width,py(t))
        c.drawRightString(plot_left-6,py(t)-2,str(t))
    for t in (0,30,60,100):
        c.drawCentredString(px(t),plot_bottom-11,f"{t}%")
    c.setDash(2,2)
    c.line(px(30),plot_bottom,px(30),plot_bottom+plot_height)
    c.setDash()
    for key, (_,color) in keep.items():
        points=[r for r in series if r["policy"]==key]
        points.sort(key=lambda r:int(r["reach_pct"]))
        line = c.beginPath()
        for i,r in enumerate(points):
            point=px(float(r["reach_pct"])),py(float(r["uplift_pp"]))
            (line.moveTo if i==0 else line.lineTo)(*point)
        c.setStrokeColor(color)
        c.setLineWidth(1.6 if key=="t_logistic" else 1.15)
        c.drawPath(line)
    return put(c,"图 4  验证集触达比例曲线。纵轴为购买率差（百分点）。",x,y-164,width,8.5,MUTED)


def holdout_contrasts(c, x, y, records):
    left, width, bottom, top = x+11, COL-26, y-186, y-38
    scale=lambda value:left + width*(value+2.5)/7.5
    c.setFont(LATIN,9)
    c.setFillColor(MUTED)
    c.setStrokeColor(GRID)
    c.setLineWidth(.6)
    for t in (-2,0,2,4):
        c.line(scale(t),bottom,scale(t),top)
        c.drawCentredString(scale(t),bottom-12,str(t))
    c.setStrokeColor(MUTED)
    c.setDash(2,2)
    c.line(scale(0),bottom,scale(0),top)
    c.setDash()
    for i,(base,label) in enumerate([("random","相对随机排序"),("rfm","相对 RFM 规则")]):
        row=records[base]
        yy=y-83-i*79
        put(c,label,x,yy+38,COL,9.8,NAVY)
        c.setFont(BOLD,11)
        c.setFillColor(NAVY)
        c.drawRightString(x+COL-5,yy+21,f"{pp(row['difference_pp'])}   {ci(row)}")
        lo,hi,point=(float(row[k]) for k in ("ci_low_pp","ci_high_pp","difference_pp"))
        c.setStrokeColor(NAVY)
        c.setLineWidth(1.5)
        c.line(scale(lo),yy,scale(hi),yy)
        for v in (lo,hi):
            c.line(scale(v),yy-3,scale(v),yy+3)
        c.circle(scale(point),yy,3.7,stroke=0,fill=1)
    return put(c,"图 5  候选模型相对各基线的配对 95% CI（百分点）。",
               x,y-208,COL,8.5,MUTED)


def page(c, number, title, deck):
    c.bookmarkPage(f"page{number}")
    c.addOutlineEntry(title,f"page{number}",level=0)
    c.setFillColor(NAVY)
    c.setFont(BOLD,11.5)
    c.drawString(M,H-37,"X5 RetailHero")
    c.setFont(LATIN,10.5)
    c.drawRightString(W-M,H-37,f"CASE STUDY  /  {number:02d}")
    c.setStrokeColor(GRID)
    c.line(M,H-48,W-M,H-48)
    put(c,title,M,H-62,WIDTH,25,NAVY,gap=4)
    put(c,deck,M,H-106,WIDTH,10.4,MUTED)
    c.setStrokeColor(GRID)
    c.line(M,32,W-M,32)
    c.setFont(CJK,8)
    c.setFillColor(MUTED)
    c.drawString(M,20,"公开竞赛数据 · 营销策略分析")
    c.setFont(LATIN,9)
    c.drawRightString(W-M,20,f"{number:02d} / 09")


def cover(c, audit, delivery, held):
    c.bookmarkPage("page1")
    c.addOutlineEntry("项目概览","page1")
    c.setFillColor(DARK)
    c.rect(0,0,W,H,stroke=0,fill=1)
    c.setFillColor(white)
    c.setFont(BOLD,17)
    c.drawString(M,H-60,"X5 RetailHero")
    c.setStrokeColor(HexColor("#4B6679"))
    c.line(M,H-77,W-M,H-77)
    put(c,"短信营销中，模型选人",M,H-110,440,34,white)
    put(c,"优于随机吗？",M,H-174,440,34,white)
    put(c,"零售客户分析 · 营销实验 · Uplift 建模",M,H-242,435,14,HexColor("#CFDCE6"))
    put(c,"公开竞赛数据离线复现。以固定触达比例比较模型、随机排序和历史消费规则，并用保留集检验是否达到采用门槛。",
        M,H-293,374,11.5,HexColor("#CFDCE6"))

    x,y,w,h=481,224,316,252
    c.setFillColor(HexColor("#1B3C57"))
    c.rect(x,y,w,h,stroke=0,fill=1)
    put(c,"独立保留集的主要发现",x+24,y+h-27,w-48,13,white)
    focus=held["random"]
    c.setFont(BOLD,56)
    c.setFillColor(white)
    c.drawString(x+24,y+126,pp(focus["difference_pp"]))
    put(c,"相对随机的优势（百分点）",x+24,y+114,w-48,11,HexColor("#CFDCE6"))
    put(c,f"配对 95% CI {ci(focus)}",x+24,y+81,w-48,12,white)
    put(c,"未确认优于随机排序。原模型用于离线预测。",x+24,y+43,w-48,9.4,HexColor("#CFDCE6"))
    c.setStrokeColor(HexColor("#4B6679"))
    c.line(M,190,W-M,190)
    items = [(next(r["rows"] for r in audit["files"] if r["table"]=="purchases"),"历史商品明细"),
             (delivery["labeled_customers"],"有标签客户"),(delivery["scored_customers"],"官方测试预测")]
    for i,(value,label) in enumerate(items):
        x=M+i*252
        c.setFont(BOLD,25)
        c.setFillColor(white)
        c.drawString(x,138,m(value))
        put(c,label,x,121,203,10.5,HexColor("#CFDCE6"))
    c.setStrokeColor(HexColor("#4B6679"))
    c.line(M,32,W-M,32)
    c.setFont(LATIN,9)
    c.setFillColor(white)
    c.drawRightString(W-M,20,"01 / 09")
    c.showPage()


def build(destination):
    setup_fonts()
    audit = data("audit","metadata/audit_summary.json")
    customer = data("customer","metadata/analysis_summary.json")
    delivery = data("delivery","metadata/submission_summary.json")
    exp = data("experiment","metadata/experiment_summary.json")
    held = {r["comparator"]:r for r in rows("holdout","tables/holdout_candidate_vs_baselines.csv")}
    val = {r["comparator"]:r for r in rows("validation","tables/candidate_vs_baselines.csv")}
    opt = rows("optimize","tables/model_summary.csv")
    segments = rows("customer","tables/segment_summary.csv")
    destination.parent.mkdir(parents=True,exist_ok=True)
    c = Canvas(str(destination),pagesize=(W,H),pageCompression=1)
    c.setTitle("X5 RetailHero | 短信营销策略分析")
    c.setSubject("作品集研究报告")
    cover(c,audit,delivery,held)

    page(c,2,"从业务问题到策略决定","同一条研究链分开回答客户价值、短信效果和模型选人这三个问题。")
    y=455
    for title,body in [
        ("研究目标","短信有触达成本。官方任务比较预测排名前 30% 人群的增量转化。本项目进一步追问，在同一触达比例下，模型能否优于随机和 RFM？"),
        ("分析单位","商品明细按订单归并，再聚合到客户。用于排序的特征都来自历史窗口，营销分组和购买结果在拟合与评估时按各自职责使用。"),
        ("评估单位","先在训练集探索和拟合，验证集筛选候选，最后用原保留集评价锁定策略。官方测试名单用于交付评分。"),
        ("阅读路线","第 3 至 5 页依次为数据审计、客户分析与短信实验。第 6 至 9 页介绍策略验证、保留集评估、优化与交付、复现。"),
    ]:
        y=heading(c,title,LEFT,y)
        y=put(c,body,LEFT,y,gap=13)
    note(c,"保留集判断先于全量重训。交付文件的完整性和策略的业务有效性分别核验。",LEFT,y)
    image(c,RESULTS/"portfolio/X5_RetailHero_研究流程图.png",RIGHT,456,COL,
          "图 1  七个阶段的输入、产出和检查点。另附高清长图。",max_height=371)
    c.showPage()

    page(c,3,"数据审计与样本设计","把订单粒度和样本边界锁定在前面，后续消费、实验和建模才能对账。")
    counts={r["table"]:r["rows"] for r in audit["files"]}
    inputs=[("clients.csv","客户资料"),("products.csv","匿名商品及品类"),("purchases.csv","历史商品明细"),
            ("uplift_train.csv","处理标记与购买结果"),("uplift_test.csv","官方测试客户名单"),
            ("uplift_sample_submission.csv","预测文件格式样例")]
    y=heading(c,"数据来源与粒度",LEFT,455)
    y=table(c,["输入文件","行数","主要用途"],
            [(name,m(counts[name[:-4]]),use) for name,use in inputs],[145,70,141],LEFT,y,8.8)
    y=put(c,"历史窗口为 2018-11-21 21:02:33 至 2019-03-18 23:40:03。RFM 统一以次日 2019-03-19 为参考，触达时点尚待核实。",LEFT,y)
    note(c,f"{m(audit['transactions'])} 笔交易按客户和交易编号归并。每笔只取一次整单金额，避免在商品明细层重复累计。",LEFT,y)
    y=heading(c,"审计发现与处理",RIGHT,455)
    for s in [
        "28 个交易编号被不同客户使用。用客户与交易编号组成订单键，检查时间、门店和总额的一致性。",
        "2,707,278 条全量明细数量为零。保留源记录，品类数量汇总时贡献为零，按明细计数时仍计入。",
        "年龄异常、兑换日期晚于窗口等情况均记录。当前模型使用购买历史特征，避免把时间来源不明的会员字段用于评分。",
    ]:
        y=put(c,s,RIGHT,y,gap=8)
    y=heading(c,"客户级固定划分",RIGHT,y-1)
    y=table(c,["集合","客户数","用途"],[("训练集","120,022","发现规律、拟合"),
         ("验证集","40,008","比较策略、选择候选"),("最终保留集","40,009","锁定后的独立评价")],
         [93,75,188],RIGHT,y)
    put(c,"按处理标记与购买结果联合分层，使用固定种子和客户编号哈希，确保集合互斥、每次运行可复现。",RIGHT,y)
    c.showPage()

    page(c,4,"客户消费、复购与品类","高价值客户占 15.1%，贡献了训练客户历史消费额的 37.3%。")
    y=heading(c,"训练客户画像",LEFT,455)
    y=table(c,["客群","客户数","人数占比","消费占比"],
            [(r["segment"],m(r["customers"]),f"{float(r['customer_share']):.1%}",
              f"{float(r['sales_share']):.1%}") for r in segments],[120,78,78,80],LEFT,y)
    y=put(c,f"{m(customer['training_customers'])} 位训练客户共 {m(customer['training_orders'])} 笔历史订单。"
            "人均订单数的中位数为 15 笔，订单加权客单价为 428.65，沿用源数据金额单位。",LEFT,y)
    y=heading(c,"分层与复购指标",LEFT,y)
    y=put(c,"高价值需要订单数至少 27 笔、累计消费至少 11,105.59。最近购买间隔以 2 天和 10 天划分。"
            "复购先按购买日去重，使用相邻购买日间隔的客户内中位数，再得到跨客户中位数 5 天。",LEFT,y)
    note(c,"高价值代表观察期内消费多、频次高。它能帮助描述客户，也可作为触达规则的对照。",LEFT,y)
    y=image(c,artifact("customer","figures/cohort_purchase_activity.png"),RIGHT,456,COL,
            "图 2  月度 cohort。横线表示整月比例不可用。")
    y=heading(c,"观察期复购与品类偏好",RIGHT,y)
    y=put(c,"2019 年 1 月首次观察到购买的 8,461 位客户中，7,241 人于 2 月再次购买，占 85.6%。"
            "首尾月份不完整，首次观察购买月也受到历史窗口左边界限制。",RIGHT,y)
    put(c,"二级品类以匿名编号表示。头部品类在明细行与正数量中的占比分别为 16.5% 和 17.5%。"
          "不把整单金额分摊给品类，零数量明细对数量汇总贡献为零。",RIGHT,y)
    c.showPage()

    page(c,5,"短信实验与客群差异","训练集上短信组购买率为 63.65%，对照组为 60.33%。观察到的差值为 +3.32 个百分点。")
    y=heading(c,"样本与整体差值",LEFT,455)
    o=exp["overall"]
    y=table(c,["组别","人数","购买人数","购买率"],
            [("短信组",m(o["sms_n"]),m(o["sms_buyers"]),p(o["sms_rate"])),
             ("对照组",m(o["control_n"]),m(o["control_buyers"]),p(o["control_rate"]))],
            [83,89,90,94],LEFT,y)
    y=put(c,f"总体差值的 95% CI 为 {ci(o)} 个百分点。历史特征的最大绝对标准化均值差为 "
          f"{exp['max_absolute_smd']:.3f}，已检查变量在组间接近。",LEFT,y)
    y=heading(c,"分群效应怎么读",LEFT,y)
    y=put(c,"先用整体差描述训练集，再做五个 RFM 群的比较。五群组内检验用 Holm 校正，联合检验提示效应存在差异。"
          "组内区间用非合并方差估计，图上显示逐项 95% CI。",LEFT,y)
    contrast=exp["high_value_contrast"]
    note(c,f"高价值待唤醒相对高价值活跃的差值为 {pp(contrast['difference_pp'])} 个百分点，"
           f"两客群差值的 95% CI 为 {ci(contrast)}。目前无法确认优先召回更有效。",LEFT,y)
    y=image(c,artifact("experiment","figures/sms_effect_forest.png"),RIGHT,456,COL,
            "图 3  短信组与对照组的总体及分群购买率差。")
    y=heading(c,"因果解释的条件",RIGHT,y)
    put(c,"购买率差需要结合分配机制解释。已有特征接近只能作为平衡诊断，项目资料尚未核实精确触达日期、"
          "结果窗口和随机分配协议。报告保留观察到的差值表述。",RIGHT,y)
    c.showPage()

    page(c,6,"六种策略的验证集比较","用同一批 40,008 位验证客户和同样的触达比例，比较不同选人规则。")
    y=heading(c,"候选模型与评分定义",LEFT,455)
    for label,body in [
        ("概率差打分","T-Learner 分别拟合短信组与对照组购买概率。对同一客户，让两条模型各给一次分数，两者相减得到预测 Uplift。"
         "比较逻辑回归和梯度提升树。S-Learner 则在同一模型中分别指定两种短信状态。"),
        ("三条参照策略","比较固定种子随机排序、基于训练集分位数的等权 RFM 排序，以及普通购买概率排序。填补、标准化和品类编码都在训练集拟合。"),
        ("统一的 30% 评价","将分数从高到低排序，平分按客户号升序。每条策略圈选 12,002 人，计算入选短信组购买率减对照组购买率。"
         "AUUC 与 Qini 分别汇总购买率差曲线与归一化累计增量曲线，每 5% 取点做梯形积分。"),
    ]:
        y=heading(c,label,LEFT,y)
        y=put(c,body,LEFT,y,gap=12)
    note(c,f"筛出的逻辑回归 T-Learner 在验证集比随机高 {pp(val['random']['difference_pp'])} 个百分点。"
           "这一批客户用于选择候选，优势需在保留集复核。",LEFT,y)
    y=heading(c,"验证结果",RIGHT,455)
    model=rows("validation","tables/validation_at30.csv")
    y=table(c,["策略","差值（百分点）","95% CI"],
            [(r["label"],pp(r["uplift_pp"]),ci(r)) for r in model],[159,86,111],RIGHT,y,8.6)
    coverage_curve(c,RIGHT,y,COL)
    c.showPage()

    page(c,7,"独立评估改变了投放判断","验证集上相对随机的领先为 +3.45 个百分点，最终保留集上缩至 +0.29。")
    y=heading(c,"锁定以后再打开结果",LEFT,455)
    y=put(c,"在 40,009 位保留客户中，每条策略选前 12,002 人。预先锁定模型、特征、排序、触达比例和基线。"
          "分数先写入文件，再关联结果。验证集重放名单和原记录一致。",LEFT,y)
    h=rows("holdout","tables/holdout_at30.csv")
    y=table(c,["策略","Uplift@30%","95% CI（百分点）"],
            [(r["label"],pp(r["uplift_pp"]),ci(r)) for r in h],[137,82,137],LEFT,y,9)
    y=heading(c,"采用门槛",LEFT,y)
    y=put(c,"直接比较候选与同预算下的两条基线。配对区间考虑两份触达名单可能选中同一客户。"
          "只有两个区间的下界都大于零才视为达到采用门槛。",LEFT,y)
    note(c,f"相对随机 {pp(held['random']['difference_pp'])}，95% CI {ci(held['random'])}。"
          f"相对 RFM {pp(held['rfm']['difference_pp'])}，95% CI {ci(held['rfm'])}。单位为百分点。",LEFT,y)
    y=holdout_contrasts(c,RIGHT,456,held)
    y=heading(c,"业务判断",RIGHT,y)
    put(c,"模型优于 RFM，相对随机的区间跨零，因此未达到锁定采用门槛。若进入真实投放，"
          "可将新客户随机分给两种选人策略，每组按相同预算触达，再比较策略整体购买率和利润。",RIGHT,y)
    c.showPage()

    page(c,8,"优化诊断与离线交付","给模型加特征之后，平均改善很小且方向不稳定。最终交付沿用原 T-Learner。")
    y=heading(c,"用重复验证检查优化",LEFT,455)
    y=put(c,"在原训练和验证的 160,030 人上做三次重复五折，随机基线按 12 个固定种子平均。"
          "新特征衡量相对个人购买间隔和两个相邻 14 天的订单数变化。正则化 S-Learner 只引入两项短信交互。",LEFT,y)
    opt_names={"base_t":"原 T-Learner","behavior_t":"T-Learner 加特征","interaction_s":"S-Learner 加特征"}
    y=table(c,["方案","平均 Uplift@30%","相对随机","领先折数"],
            [(opt_names[r["model"]],pp(r["mean_uplift_pp"]),pp(r["mean_vs_random_pp"]),
              f"{r['folds_positive_vs_random']}/15") for r in opt],[126,109,60,61],LEFT,y,8.9)
    image(c,artifact("optimize","figures/repeated_cv_uplift.png"),LEFT,y,COL,
          "图 6  重复验证只用于开发诊断。各次重复使用相同客户池。",max_height=160)
    y=heading(c,"交付完成情况",RIGHT,455)
    y=table(c,["项目","结果"],[
        ("全量重训",f"{m(delivery['labeled_customers'])} 位有标签客户"),
        ("官方测试客户",f"{m(delivery['scored_customers'])} 位"),
        ("输出","client_id,uplift"),
        ("完整性","客户唯一、覆盖完整、样例顺序一致"),
        ("复现","重跑预测文件逐字节一致"),
    ],[109,247],RIGHT,y)
    y=put(c,"新增特征的 T-Learner 在三次重复中两次略好，一次变差，平均只比原模型高 0.02 个百分点。"
          "独立保留集仍是原模型策略评价的依据。",RIGHT,y)
    note(c,"全量重训纳入全部有标签客户。公开官方测试集只有客户名单，预测文件经过格式核验，"
           "项目的独立效果数字来自本地保留集。",RIGHT,y)
    c.showPage()

    page(c,9,"复现、证据与结论边界","从工作目录可以逐阶段找到数据核验、方法代码、折外分数和最终预测。")
    y=heading(c,"复现路径",LEFT,455)
    y=table(c,["阶段","执行文件"],[
        ("审计与特征","01_audit_data.py · 02_customer_analysis.py"),
        ("短信实验","03_sms_experiment.py"),
        ("模型与验证","04_build_validation_features.py · 04_uplift_baselines.py"),
        ("独立评价","05_holdout_evaluation.py"),
        ("正式预测","06_build_test_features.py · 06_official_test_delivery.py"),
        ("优化诊断","07_build_behavior_features.py · 07_optimize_uplift.py")
    ],[94,262],LEFT,y,8.5)
    y=put(c,"主要工具为 Python、Pandas、NumPy、SQLite、scikit-learn 和 Matplotlib。"
          "审计、特征或模型结果按阶段保存在 results/，相关核验记录在 metadata/。",LEFT,y)
    put(c,"流程图与本报告可分别由 plot_portfolio_workflow.py 和 build_portfolio_report.py 重新生成。",LEFT,y)
    y=heading(c,"证据边界",RIGHT,455)
    for text in [
        "购买日志的结束日用于计算相对时间，精确触达日、标签窗口和分配协议仍待核实。",
        "验证集的最佳分数受到模型选择影响。重复交叉验证用于筛选方向，保留集结论来自锁定方案。",
        "历史排行榜与项目的本地保留集属于不同样本。利润评估还需短信成本和每笔增量购买毛利。",
    ]:
        y=put(c,text,RIGHT,y,gap=8)
    y=heading(c,"外部资料",RIGHT,y)
    sources=[
        ("Open Data Science 竞赛说明","https://ods.ai/competitions/x5-retailhero-uplift-modeling"),
        ("Open Data Science 数据与提交格式","https://ods.ai/competitions/x5-retailhero-uplift-modeling/data"),
        ("Open Data Science 历史排行榜","https://ods.ai/competitions/x5-retailhero-uplift-modeling/leaderboard"),
        ("Künzel 等，Meta-learners，PNAS 2019","https://doi.org/10.1073/pnas.1804597116"),
        ("Cawley 与 Talbot，模型选择偏差，JMLR 2010","https://www.jmlr.org/papers/volume11/cawley10a/cawley10a.pdf"),
    ]
    for title,url in sources:
        y2=put(c,title,RIGHT,y,COL,9.6,NAVY,gap=3)
        c.linkURL(url,(RIGHT,y2+2,RIGHT+COL,y),relative=0,thickness=0)
        y=y2
    c.showPage()
    c.save()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEST)
    build(parser.parse_args().output)


if __name__ == "__main__":
    main()
