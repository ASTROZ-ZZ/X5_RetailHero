#!/usr/bin/env python3
"""Publish the management report, editorial portfolio and workflow board."""

import argparse
from html import escape
from pathlib import Path
import re

from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Flowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from build_powerbi_report import LABELS, ROOT, collect, metadata, rows


W, H = 960, 600
INK = HexColor("#27183E")
VIOLET = HexColor("#5A36A3")
DEEP = HexColor("#281742")
PLUM = HexColor("#3B235E")
LILAC = HexColor("#E8DFF6")
GOLD = HexColor("#F1CC52")
OCHRE = HexColor("#AC7C14")
PALE = HexColor("#FAF0C3")
PAPER = HexColor("#FAF8F3")
MUTED = HexColor("#61586F")
GRID = HexColor("#D9D0E3")
SMOKE = HexColor("#B8A6D3")
FONTS = Path("/System/Library/Fonts")
DEST = ROOT / "results" / "reporting"
ZH_T, ZH_B, EN, EN_B = "X5-Heiti", "X5-Songti", "X5-Times", "X5-Times-Bold"
LATIN = re.compile(r"([A-Za-zÀ-ÖØ-öø-ÿ0-9+\-\[\]()/.,%=&:<>–]+(?:[ ][A-Za-zÀ-ÖØ-öø-ÿ0-9+\-\[\]()/.,%=&:<>–]+)*)")


def fonts():
    specs = [(ZH_T, FONTS / "STHeiti Medium.ttc", 1),
             (ZH_B, FONTS / "Supplemental/Songti.ttc", 6),
             (EN, FONTS / "Supplemental/Times New Roman.ttf", 0),
             (EN_B, FONTS / "Supplemental/Times New Roman Bold.ttf", 0)]
    for alias, file, index in specs:
        pdfmetrics.registerFont(TTFont(alias, str(file), subfontIndex=index))


def mixed_text(value, heading=False):
    return "".join(
        f'<font name="{EN_B if heading else EN}">{escape(part)}</font>' if i % 2 else escape(part)
        for i, part in enumerate(LATIN.split(str(value)))
    )


def paragraph(c, value, x, top, width, size=13, color=INK, heading=False, leading=None):
    p = Paragraph(mixed_text(value, heading), ParagraphStyle("p", fontName=ZH_T if heading else ZH_B,
                  fontSize=size, textColor=color, leading=leading or size * 1.43, wordWrap="CJK",
                  allowWidows=1, allowOrphans=1))
    _, height = p.wrap(width, 1100)
    if top - height < 0:
        raise ValueError(f"Text outside page at {top}: {value}")
    p.drawOn(c, x, top - height)
    return top - height


def label(c, value, x, top, width=600, size=10, color=MUTED, heading=None):
    if heading is None:
        heading = size >= 12 if getattr(c, "_x5_portfolio", False) else True
    return paragraph(c, value, x, top, width, size, color, heading)


def rect(c, x, y, width, height, color):
    c.setFillColor(color)
    c.rect(x, y, width, height, fill=1, stroke=0)


def rule(c, x, y, x2, y2=None, color=GRID, weight=.8, dashed=False):
    c.saveState()
    c.setStrokeColor(color)
    c.setLineWidth(weight)
    if dashed:
        c.setDash(3, 3)
    c.line(x, y, x2, y if y2 is None else y2)
    c.restoreState()


def circle(c, x, y, radius, color):
    c.setFillColor(color)
    c.circle(x, y, radius, fill=1, stroke=0)


def rings(c, x, y, r, n=8):
    c.saveState()
    c.setStrokeColor(HexColor("#6D4E97"))
    c.setLineWidth(.7)
    for i in range(n):
        c.circle(x, y, r * (i + 1) / n, fill=0, stroke=1)
    c.restoreState()


def serif(c, value, x, y, size, color=INK, right=False):
    c.setFillColor(color)
    c.setFont(EN_B, size)
    (c.drawRightString if right else c.drawString)(x, y, str(value))


def portfolio_footer(c, page, total, dark=False):
    serif(c, f"{page:02d}  /  {total:02d}", 918, 21, 10.5, LILAC if dark else MUTED, right=True)
    c.showPage()


def frame(c, kicker, title, deck):
    rect(c, 0, 0, W, H, PAPER)
    rect(c, 42, 552, 23, 5, GOLD)
    label(c, kicker, 75, 565, color=VIOLET, size=11)
    label(c, title, 42, 535, 880, 31, INK)
    paragraph(c, deck, 43, 482, 875, 13, MUTED)


def grid_table(c, x, top, widths, headings, body, row_h=31, size=11, emphasis=()):
    width = sum(widths)
    padding = min(7, max(1.25, (row_h - 1.43 * size) / 2))
    rect(c, x, top-row_h, width, row_h, PLUM)
    for i, item in enumerate(headings):
        label(c, item, x+sum(widths[:i])+8, top-padding, widths[i]-16, size, white, heading=True)
    for row_num, row in enumerate(body):
        y = top-(row_num+1)*row_h
        rect(c, x, y-row_h, width, row_h,
             PALE if row_num in emphasis else white if row_num % 2 == 0 else LILAC)
        for i, item in enumerate(row):
            end = paragraph(c, item, x+sum(widths[:i])+8, y-padding, widths[i]-16, size)
            if end < y-row_h+1:
                raise ValueError(f"Row too short: {item}")
    return top-(len(body)+1)*row_h


def forest(c, x, y, w, h, entries, minimum, maximum, ticks):
    left, right = x+133, x+w-120
    baseline, top = y+28, y+h-15
    def scale(v):
        return left + (right-left)*(v-minimum)/(maximum-minimum)
    for t in ticks:
        xpos = scale(t)
        rule(c, xpos, baseline, xpos, top, MUTED if t == 0 else GRID, .8, t == 0)
        serif(c, str(t), xpos+4, y+9, 9, MUTED, right=True)
    for i, (name, point, low, high) in enumerate(entries):
        yy = top - (i+.5)*(top-baseline)/len(entries)
        label(c, name, x, yy+7, 129, 10.5, INK)
        tone = VIOLET if low > 0 else OCHRE
        rule(c, scale(low), yy, scale(high), color=tone, weight=1.7)
        for bound in (low, high):
            xx = scale(bound)
            rule(c, xx, yy-3, xx, yy+3, tone, .9)
        circle(c, scale(point), yy, 3.4, tone)
        paragraph(c, f"{point:+.2f}  [{low:+.2f}, {high:+.2f}]", right+9, yy+7, 115, 10.2)


def pair(row, name, key):
    return (name, float(row[key]), float(row["ci_low_pp"]), float(row["ci_high_pp"]))


def segment_bars(c, x, y, w, h, entries):
    chart_l = x + 112
    chart_r = x + w-44
    def xpos(frac):
        return chart_l+(chart_r-chart_l)*frac/.4
    for frac in (0, .1, .2, .3, .4):
        xx = xpos(frac)
        rule(c, xx, y+18, xx, y+h-24)
        serif(c, f"{frac:.0%}", xx+8, y+5, 8.5, MUTED, right=True)
    spacing = (h-48)/len(entries)
    bar_height = min(7, spacing/3)
    for i, r in enumerate(entries):
        yy = y+h-38-i*spacing
        label(c, r["segment"], x, yy+9, 110, 10.5, INK)
        for j, (key, tone) in enumerate([("customer_share", GOLD), ("sales_share", VIOLET)]):
            v = float(r[key])
            bar = yy+1-j*(bar_height+2)
            rect(c, chart_l, bar, xpos(v)-chart_l, bar_height, tone)
            serif(c, f"{v:.1%}", xpos(v)+4, bar, 8.5, INK)
    for j, (name, tone) in enumerate([("客户占比", GOLD), ("历史消费额占比", VIOLET)]):
        xx = x+116+j*100
        rect(c, xx, y+h-12, 8, 8, tone)
        label(c, name, xx+12, y+h-2, 100, 9.5, MUTED)


def coverage_chart(c, x, y, w, h, records):
    left, right, bottom, top = x+27, x+w-17, y+26, y+h-30
    def xx(v):
        return left+(right-left)*v
    def yy(v):
        return bottom+(top-bottom)*(v+2)/12
    for v in (0, 2, 4, 6, 8, 10):
        rule(c, left, yy(v), right, color=GRID if v else MUTED)
        serif(c, v, left-7, yy(v)-3, 9, MUTED, right=True)
    for v in (0, .3, .5, .75, 1):
        serif(c, f"{v:.0%}", xx(v)+8, y+10, 9, MUTED, right=True)
    rule(c, xx(.3), bottom, xx(.3), top, MUTED, .8, True)
    for i, (name, tone) in enumerate([("T-Learner", VIOLET), ("随机排序", OCHRE), ("RFM 规则", SMOKE)]):
        s = sorted((q, score) for q, model, score in records if name == model)
        c.setStrokeColor(tone)
        c.setLineWidth(2)
        path = c.beginPath()
        path.moveTo(xx(s[0][0]), yy(s[0][1]))
        for q, n in s[1:]:
            path.lineTo(xx(q), yy(n))
        c.drawPath(path)
        for q, n in s:
            if q == .3:
                circle(c, xx(q), yy(n), 3.4, tone)
        rec_x = x+28+i*min(126, (w-35)/3)
        rect(c, rec_x, y+h-16, 11, 3, tone)
        display_name = {"T-Learner": "模型选客", "随机排序": "随机选客", "RFM 规则": "历史价值选客"}.get(name, name) if getattr(c, "_x5_portfolio", False) else name
        label(c, display_name, rec_x+16, y+h-7, 108, 9.5, MUTED)


def flow_steps(c, x, y, w, items, dark=False):
    step = w/len(items)
    under = LILAC if dark else MUTED
    action = white if dark else INK
    rule(c, x+10, y+38, x+w-step+10, color=SMOKE if dark else GRID, weight=1.2)
    for i, (title, subtitle) in enumerate(items):
        xx = x+i*step
        circle(c, xx+10, y+38, 9, GOLD if i in (0, len(items)-1) else VIOLET)
        label(c, title, xx, y+23, step-5, 12, action)
        paragraph(c, subtitle, xx, y+1, step-9, 10, under)


def pct(v, digits=1):
    return f"{float(v):.{digits}%}"


def pp(v):
    return f"{float(v):+.2f}"


def ci(row):
    return f"[{pp(row['ci_low_pp'])}, {pp(row['ci_high_pp'])}]"


class Results:
    def __init__(self):
        self.aggregates = collect()
        self.segments = rows("02_customer_analysis", "segment_summary")
        self.effect = rows("03_sms_experiment", "purchase_rate_effects")
        self.validation = rows("04_uplift_baselines", "validation_at30")
        self.hold = rows("05_holdout_evaluation", "holdout_at30")
        self.vp = rows("04_uplift_baselines", "candidate_vs_baselines")
        self.hp = rows("05_holdout_evaluation", "holdout_candidate_vs_baselines")
        self.opt = rows("07_uplift_optimization", "model_summary")
        self.curves = self.aggregates["Curves"][1]
        self.overview = self.aggregates["Overview"][1][0]
        self.audit = metadata("01_data_audit", "audit_summary")
        self.summary = metadata("06_offline_delivery", "submission_summary")
        self.cohort = self.aggregates["Cohort"][1]

    @property
    def paired(self):
        return [pair(self.vp[0], "验证 · 对随机", "difference_pp"),
                pair(self.hp[0], "保留 · 对随机", "difference_pp"),
                pair(self.hp[1], "保留 · 对 RFM", "difference_pp")]


WORKFLOW = [("审计", "六张源表"), ("画像", "RFM 与复购"), ("实验", "短信与对照"),
            ("建模", "固定预算排序"), ("保留评估", "配对比较"),
            ("交付与优化", "原模型留作候选")]


REPORT_SECTIONS = (
    ("一、数据来源与分析设计", ("数据来源与清洗", "样本划分与评估路径")),
    ("二、客户行为与价值分层", ("RFM 分层与消费贡献", "复购、品类与业务应用")),
    ("三、短信营销实验分析", ("总体购买率差", "客群差异与统计口径")),
    ("四、增量模型与验证集比较", ("模型与对照策略", "验证结果与候选选择")),
    ("五、独立保留集评估", ("固定触达比例下的策略结果", "配对区间与采用门槛")),
    ("六、模型优化与离线交付", ("开发集优化比较", "官方待评客户离线评分")),
    ("七、结论与试点建议", ("离线结论", "同预算随机试点")),
    ("八、指标口径与参考资料", ("主要指标与解释边界", "数据来源与复核路径")),
)


class ReportFigure(Flowable):
    def __init__(self, width, height, draw):
        super().__init__()
        self.width, self.height = width, height
        self.hAlign = "CENTER"
        self.draw_figure = draw

    def draw(self):
        self.draw_figure(self.canv, self.width, self.height)


class ResearchReport(SimpleDocTemplate):
    def afterFlowable(self, flowable):
        if hasattr(flowable, "bookmark"):
            self.canv.bookmarkPage(flowable.bookmark)
            self.canv.addOutlineEntry(flowable.getPlainText(), flowable.bookmark)


def report_cover(c, doc):
    w, h = doc.pagesize
    rect(c, 0, 0, w, h, PAPER)
    rect(c, 0, 0, w, 303, DEEP)
    rect(c, 59, 749, 39, 4, GOLD)
    label(c, "X5 RETAILHERO", 60, 734, 474, 17, VIOLET)
    label(c, "零售客户洞察与", 57, 632, 482, 43, INK)
    label(c, "短信增量策略评估", 57, 566, 482, 43, INK)
    paragraph(c, "基于 X5 RetailHero 公开交易与营销数据的企业决策报告", 62, 472, 459, 15, MUTED)
    rule(c, 61, 386, 535, color=GRID)
    label(c, "客户价值分层  /  短信实验  /  增量排序", 61, 364, 470, 12, INK)
    c.saveState()
    clip = c.beginPath()
    clip.rect(0, 0, w, 303)
    c.clipPath(clip, fill=0, stroke=0)
    rings(c, 449, 152, 260, 11)
    c.restoreState()
    circle(c, 449, 152, 65, GOLD)
    serif(c, "X5", 411, 131, 42, DEEP)


def report_page(c, doc):
    w, h = doc.pagesize
    rect(c, 58, h-42, 20, 3, GOLD)
    label(c, "X5 RetailHero  /  零售客户洞察与短信增量策略评估", 85, h-30, 450, 9, MUTED)
    rule(c, 58, h-51, w-58, color=GRID, weight=.65)
    if doc.page >= 4:
        c.setFont(EN, 10.5)
        c.setFillColor(MUTED)
        c.drawCentredString(w/2, 32, str(doc.page-3))


def report_toc(c, width, height):
    for i, (title, subsections) in enumerate(REPORT_SECTIONS):
        top = height-i*63
        label(c, title, 0, top, width-32, 13, INK)
        title_width = pdfmetrics.stringWidth(title, ZH_T, 13)
        rule(c, title_width+13, top-12, width-26, color=SMOKE, weight=.65, dashed=True)
        serif(c, i+1, width-2, top-13, 12, VIOLET, right=True)
        c.linkRect("", f"chapter-{i+1}", (0, top-55, width, top+1),
                   relative=1, thickness=0)
        for j, subsection in enumerate(subsections):
            paragraph(c, f"（{'一二'[j]}）{subsection}", 15, top-20-j*17,
                      width-30, 10.5, MUTED)


def enterprise_story(d, doc_width):
    head = ParagraphStyle("chapter", fontName=ZH_T, fontSize=19, leading=28,
                          spaceAfter=21, textColor=INK, wordWrap="CJK", alignment=TA_CENTER)
    topic = ParagraphStyle("topic", fontName=ZH_T, fontSize=12.5, leading=19,
                           spaceBefore=8, spaceAfter=5, textColor=DEEP, wordWrap="CJK",
                           keepWithNext=True)
    prose = ParagraphStyle("prose", fontName=ZH_B, fontSize=11.8, leading=20,
                           spaceAfter=8, textColor=INK, wordWrap="CJK", firstLineIndent=23.6)
    caption = ParagraphStyle("caption", fontName=ZH_B, fontSize=10.5, leading=15,
                             spaceBefore=4, spaceAfter=9, alignment=TA_CENTER, textColor=MUTED)
    note = ParagraphStyle("source", fontName=ZH_B, fontSize=9.5, leading=15,
                          spaceAfter=8, textColor=MUTED, wordWrap="CJK")
    cell = ParagraphStyle("table-text", fontName=ZH_B, fontSize=10.8, leading=15,
                          textColor=INK, wordWrap="CJK")
    table_head = ParagraphStyle("table-heading", parent=cell, fontName=ZH_T, textColor=DEEP)
    table_title = ParagraphStyle("table-title", parent=caption, keepWithNext=True)
    story = [Spacer(1, 1), PageBreak()]

    def add(value, style=prose, heading=False):
        story.append(Paragraph(mixed_text(value, heading), style))

    def part(chapter, section):
        add(f"（{'一二'[section]}）{REPORT_SECTIONS[chapter-1][1][section]}", topic, True)

    def chapter(number):
        story.append(PageBreak())
        heading = Paragraph(mixed_text(REPORT_SECTIONS[number-1][0], True), head)
        heading.bookmark = f"chapter-{number}"
        story.append(heading)

    def figure(title, draw, height, source=None):
        story.extend([ReportFigure(doc_width, height, draw), Paragraph(mixed_text(title), caption)])
        if source:
            add(source, note)

    def table(title, headers, data, widths):
        add(title, table_title)
        cells = [[Paragraph(mixed_text(str(v), True), table_head) for v in headers]]
        cells.extend([Paragraph(mixed_text(str(v)), cell) for v in row] for row in data)
        t = Table(cells, colWidths=widths, hAlign="CENTER", repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), LILAC),
            ("LINEABOVE", (0, 0), (-1, 0), .8, VIOLET),
            ("LINEBELOW", (0, 0), (-1, 0), .45, GRID),
            ("LINEBELOW", (0, -1), (-1, -1), .8, VIOLET),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, HexColor("#F9F7FC")]),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.extend([t, Spacer(1, 12)])

    add("摘  要", head, True)
    add("本报告基于 X5 RetailHero 的公开零售数据，识别消费贡献较高的客户，估计历史短信活动的组间购买率差，并在相同触达比例下比较增量模型及基线的排序效果。历史样本覆盖 400,162 位客户和 45,786,568 条商品交易明细。")
    add("分析先按客户与交易编号还原订单，再依据近期购买、交易频次和消费金额建立 RFM 客群画像。带实验标签的客户分为训练集、验证集和独立保留集。训练集用于画像、短信效果估计和模型拟合，验证集用于筛选排序策略，独立保留集用于评价已锁定的模型及规则。")
    add(f"高价值客户占训练样本的 {pct(d.overview[6])}，贡献 {pct(d.overview[7])} 的历史消费额。短信组购买率为 {pct(d.effect[0]['sms_rate'], 2)}，对照组为 {pct(d.effect[0]['control_rate'], 2)}，相差 {pp(d.effect[0]['difference_pp'])} 个百分点，95% 置信区间为 {ci(d.effect[0])}。活动分配协议尚需核实。")
    add(f"固定触达比例为 30% 时，逻辑回归 T-Learner 在验证集相对随机排序领先 {pp(d.vp[0]['difference_pp'])} 个百分点。独立保留集内，其领先幅度为 {pp(d.hp[0]['difference_pp'])} 个百分点，配对 95% 置信区间为 {ci(d.hp[0])}，跨过零。增加行为特征后，开发集重复交叉验证的平均改进为 0.02 个百分点。")
    add("现阶段保留原模型作为候选。若要决定是否扩大应用，建议开展同预算随机试点，按策略分组比较全部入组客户的购买率，结合短信费用、优惠核销与增量毛利评估净贡献。")
    story.append(Spacer(1, 8))
    add("关键词　RFM 分层、短信营销、增量模型、独立保留集、Power BI", note)

    story.append(PageBreak())
    add("目  录", head, True)
    story.append(ReportFigure(doc_width, 504, report_toc))

    chapter(1)
    part(1, 0)
    raw = {r["table"]: r["rows"] for r in d.audit["files"]}
    add(f"项目使用六张源表。全量商品明细按客户和交易编号聚合，识别出 {d.audit['transactions']:,} 笔订单。由于 28 个交易编号被不同客户复用，使用客户编号与交易编号组成订单键。")
    table("表 1　源表规模及分析用途", ("数据表", "记录数", "分析用途"), [
        ("商品交易明细", f"{raw['purchases']:,}", "按商品行记录历史购买"),
        ("历史客户", f"{raw['clients']:,}", "客户维度"),
        ("商品", f"{raw['products']:,}", "商品与匿名品类维度"),
        ("带实验标签的客户", f"{raw['uplift_train']:,}", "处理标记与购买结果"),
        ("官方待评分客户", f"{raw['uplift_test']:,}", "客户编号与待评分范围"),
        ("官方提交样例", f"{raw['uplift_sample_submission']:,}", "提交列与客户顺序"),
    ], [153, 103, doc_width-256])
    add("历史窗口为 2018 年 11 月 21 日至 2019 年 3 月 18 日，RFM 参考日为 2019 年 3 月 19 日。公开资料尚不足以核实精确短信日期和结果观察窗口。")
    part(1, 1)
    add("项目按短信标记与购买结果联合分层，以固定散列顺序划分 200,039 位带标签客户。训练、验证和独立保留阶段分工如下。官方另有一套待评分样本。")
    table("表 2　固定样本划分及职责", ("样本", "客户数", "用途"), [
        ("训练集", "120,022", "画像、短信实验估计、模型拟合"),
        ("验证集", "40,008", "在固定触达比例下比较策略并选型"),
        ("独立保留集", "40,009", "评估锁定模型并核对采用门槛"),
    ], [153, 103, doc_width-256])
    add("来源　项目第 01 阶段数据检查报告和样本划分。", note)

    chapter(2)
    part(2, 0)
    add("固定训练集覆盖 2,411,872 笔历史订单。高价值客户需同时达到至少 27 笔订单和至少 11,105.59 的累计消费额。距末次购买至少 10 天的高价值客户归入待唤醒群。金额沿用源数据单位。")
    add(f"高价值活跃与高价值待唤醒两群合计占客户总数的 {pct(d.overview[6])}，贡献 {pct(d.overview[7])} 的历史消费额。图 1 对照了五类客户的规模和消费贡献。")
    figure("图 1　各客群的客户占比与历史消费额占比",
           lambda c, w, h: segment_bars(c, 2, 0, w-4, h-4, d.segments), 202,
           "来源　项目第 02 阶段客户分层汇总表。")
    part(2, 1)
    add("订单加权客单价为 428.65，客户复购间隔的中位数为 5 天。2019 年 1 月同群的 8,461 位客户中，有 7,241 位在 2 月再次购买，复购率为 85.6%。同群以窗口内首次观察到的购买划分，整月复购比较排除部分月份。")
    add("按明细行数排序，第一匿名二级品类占 16.5%。历史消费贡献可用于会员维护和营销分层。是否优先向高价值客群发送短信，需结合实验估计。")

    chapter(3)
    part(3, 0)
    overall = d.effect[0]
    add(f"训练集中，短信组 {int(overall['sms_n']):,} 人，对照组 {int(overall['control_n']):,} 人。两组购买率分别为 {pct(overall['sms_rate'], 2)} 和 {pct(overall['control_rate'], 2)}，相差 {pp(overall['difference_pp'])} 个百分点，逐项 95% 置信区间为 {ci(overall)}。")
    add("历史协变量的最大绝对标准化均值差（SMD）为 0.011。组间在已观察特征上接近，因果解释仍取决于实验分配协议和记录口径。")
    figure("图 2　短信组相对对照组的购买率差与 95% 置信区间（百分点）",
           lambda c, w, h: forest(c, 0, 0, w, h,
                                 [pair(r, r["segment"], "difference_pp") for r in d.effect],
                                 -3, 11, [-2, 0, 2, 4, 6, 8, 10]), 215,
           "来源　项目第 03 阶段短信营销实验分析。")
    part(3, 1)
    add("联合检验提示各客群效果存在异质性。对高价值待唤醒群和高价值活跃群进行直接比较，差值为 +3.76 个百分点，95% 置信区间为 [-2.04, +9.56]。可将这一召回假设纳入新试点。")
    add("图中的区间为逐项 95% 置信区间，采用独立客户、非合并方差的近似方法。五个客群的组内显著性使用 Holm 校正。")

    chapter(4)
    part(4, 0)
    add("T-Learner 分别拟合短信组和对照组的购买概率，以两者之差为客户排序。特征取自历史交易，缺失填补、标准化和品类编码均在训练阶段拟合。验证集有 40,008 位客户，每种策略取排序前 12,002 位。")
    table("表 3　验证集前 30% 触达时的策略比较", ("策略", "差值（百分点）", "AUUC", "Qini"), [
        (r["label"], pp(r["uplift_pp"]), f"{float(r['auuc']):.3f}", f"{float(r['qini']):.3f}")
        for r in d.validation
    ], [173, 134, 77, doc_width-384])
    figure("图 3　验证集不同触达比例下的名单内购买率差（百分点）",
           lambda c, w, h: coverage_chart(c, 7, 0, w-14, h-3, d.curves), 170)
    part(4, 1)
    add(f"逻辑回归 T-Learner 的名单内购买率差最高，为 {pp(d.validation[0]['uplift_pp'])} 个百分点。相对随机排序领先 {pp(d.vp[0]['difference_pp'])} 个百分点，配对区间 {ci(d.vp[0])}。由于同一验证集也用于选型，该区间按探索性结果解读。AUUC 与 Qini 用于在本项目统一口径下比较策略。")
    add("来源　项目第 04 阶段 Uplift 基线验证。", note)

    chapter(5)
    part(5, 0)
    add("独立保留集有 40,009 位客户。按验证阶段锁定的规则为各策略生成排名，各取前 12,002 位，再关联实验标签计算效果。表 4 反映各名单内部短信组与对照组的购买率差。")
    table("表 4　独立保留集前 30% 触达时的购买率差", ("策略", "差值（百分点）", "95% 置信区间"), [
        (LABELS[r["policy"]], pp(r["uplift_pp"]), ci(r)) for r in d.hold
    ], [174, 132, doc_width-306])
    figure("图 4　候选模型相对各基线的配对差值（百分点）",
           lambda c, w, h: forest(c, 0, 0, w, h, d.paired, -2, 6, [-2, 0, 2, 4, 6]), 147,
           "图中同时列出验证集对随机排序的结果，供对照。")
    part(5, 1)
    add(f"采用门槛要求模型相对随机排序和 RFM 规则的配对区间下限均高于零。模型相对 RFM 规则领先 {pp(d.hp[1]['difference_pp'])} 个百分点，区间为 {ci(d.hp[1])}。相对随机排序领先 {pp(d.hp[0]['difference_pp'])} 个百分点，区间为 {ci(d.hp[0])}，尚未达到预设门槛。")
    add("配对区间已考虑触达名单重叠。策略差值从未四舍五入的原始估计量计算，因此表中四舍五入后的差值再相减可能相差 0.01 个百分点。")
    add("来源　项目第 04 阶段验证结果及第 05 阶段最终保留集评估。", note)

    chapter(6)
    part(6, 0)
    add("优化使用训练集与验证集组成的 160,030 位开发客户，进行 3 次重复、每次 5 折的交叉验证。每折的随机基线取 12 个固定种子的平均结果。")
    add("新增两项行为特征。一项用距上次购买的天数与个人历史复购间隔的比值衡量节奏偏离。另一项比较相邻两个 14 天窗口的订单量，反映近期活跃变化。")
    table("表 5　开发集重复交叉验证结果（差值单位为百分点）", ("模型", "平均领先随机", "平均领先原模型", "胜出折数"), [
        (LABELS[r["model"]], pp(r["mean_vs_random_pp"]), pp(r["mean_vs_base_t_pp"]),
         "—" if r["model"] == "base_t" else r["folds_positive_vs_base_t"]+"/15")
        for r in d.opt
    ], [158, 106, 120, doc_width-384])
    add("增强模型平均只领先原模型 0.02 个百分点，在 15 折中有 9 折领先，各次重复的方向有波动。重复折共享部分客户，结果用于诊断优化方向。现阶段继续使用原模型规格。")
    part(6, 1)
    add(f"按原模型规格使用 {d.summary['labeled_customers']:,} 位带标签客户重拟合，并按官方模板为 {d.summary['scored_customers']:,} 位客户生成分数。官方测试标签未公开，本项目未取得官方测试效果指标。模型替换或新增投放仍需使用新样本评估。")
    add("来源　项目第 06 阶段离线交付、第 07 阶段优化诊断。", note)

    chapter(7)
    part(7, 0)
    add("历史短信组的购买率高于对照组。按同等触达比例比较名单时，独立保留集尚未确认模型相对随机排序的优势。基于现有证据，应保留原模型作为试点候选。")
    part(7, 1)
    actions = [
        ("1. 确定合格客群并随机分流", "从同一合格客群中随机分配到模型策略组与随机策略组。可按门店或重点客群分层，并预先定义去重、排除规则与归因窗口。"),
        ("2. 对齐触达比例和成本", "两组分别依据各自的策略选取 30% 的客户发送短信。统一内容、优惠和发送时间，记录送达、折扣和实际费用。"),
        ("3. 预先锁定指标和采用门槛", "以全部入组客户的购买率差为主要指标，按原随机分配的策略组计算。依据商业上最小有意义的差值设计样本量并报告置信区间。"),
        ("4. 复核净贡献和客户反馈", "记录增量毛利、优惠与触达成本，监控退订和投诉。策略优势与净贡献均达到预设门槛后，再讨论扩大投放。"),
    ]
    for title, description in actions:
        add(title, topic, True)
        add(description)
    add("以上试点根据离线证据提出，尚未实施。", note)

    chapter(8)
    part(8, 0)
    table("表 6　核心指标与解读", ("指标", "定义与解读"), [
        ("购买率差（百分点）", "同一分析人群内短信组购买率减去对照组购买率，再乘以 100。"),
        ("排序领先（百分点）", "候选名单内购买率差减去基准名单内购买率差。配对区间考虑了两份名单的重叠。"),
        ("AUUC 与 Qini", "验证集覆盖曲线的汇总指标，按项目定义用于策略比较。"),
    ], [149, doc_width-149])
    add("因果解释需核实活动分配机制与记录口径。报表包含汇总结果，金额保留源数据单位。本项目未估计实际增量收入或利润。")
    part(8, 1)
    references = [
        ("[1] X5 RetailHero Uplift Modeling 竞赛与公开数据",
         "https://ods.ai/competitions/x5-retailhero-uplift-modeling/data"),
        ("[2] Künzel 等（2019），估计异质性处理效应的元学习方法",
         "https://doi.org/10.1073/pnas.1804597116"),
    ]
    for title, url in references:
        story.append(Paragraph(f'<link href="{url}" color="#5A36A3">{mixed_text(title)}</link>', note))
    add("项目第 01 至 07 阶段的报告、汇总表和锁定元数据均位于 results 目录，可按研究阶段复核。配套 Power BI 项目内嵌图表所需的汇总数据，作品集提供对应的静态看板预览。")

    return story


def enterprise(path, d):
    doc = ResearchReport(str(path), pagesize=A4, leftMargin=58, rightMargin=58,
                         topMargin=74, bottomMargin=58, pageCompression=1,
                         title="X5 RetailHero 企业决策报告",
                         subject="零售客户洞察、短信营销实验与增量策略")
    doc.build(enterprise_story(d, doc.width-12), onFirstPage=report_cover, onLaterPages=report_page)


PORTFOLIO_POLICIES = {
    "t_logistic": "模型选客", "random": "随机选客", "rfm": "历史价值选客",
}
PORTFOLIO_MODELS = {
    "base_t": "原选客方案", "behavior_t": "增加行为信息的方案",
    "interaction_s": "备选选客方案",
}


def preview_panel(c, x, y, w, h, title):
    rect(c, x, y, w, h, white)
    label(c, title, x+11, y+h-9, w-22, 12.5, INK)


def preview_slicer(c, title, options):
    rect(c, 18, 315, 684, 34, white)
    label(c, title, 25, 337, 81, 10, MUTED)
    width = min(117, 578/len(options))
    for i, name in enumerate(options):
        x = 108+i*width
        rect(c, x, 321, width-5, 22, LILAC)
        label(c, name, x+7, 339, width-14, 10, INK)


def preview_overview(c, d):
    cards = [("商品交易明细", f"{d.overview[0]:,}"),
             ("历史客户", f"{d.overview[1]:,}"),
             ("短信购买率差（百分点）", pp(d.overview[4])),
             ("比随机选客高（百分点）", pp(d.overview[5]))]
    for i, (title, value) in enumerate(cards):
        x = 18 + i*173
        rect(c, x, 280, 166, 68, white)
        label(c, title, x+9, 339, 149, 10.3, MUTED)
        serif(c, value, x+9, 293, 28, VIOLET)
    preview_panel(c, 18, 51, 336, 215, "客户占比与消费额占比")
    segment_bars(c, 27, 61, 318, 172, d.segments)
    preview_panel(c, 364, 118, 338, 148, "独立检验 · 覆盖 30% 客户")
    tab = [(PORTFOLIO_POLICIES[r["policy"]], pp(r["uplift_pp"]), ci(r)) for r in d.hold]
    grid_table(c, 375, 235, [118, 78, 120], ("策略", "差值 (pp)", "95%估计范围(pp)"), tab,
               row_h=25, size=10, emphasis=(0,))
    rect(c, 364, 51, 338, 57, PALE)
    label(c, "当前状态", 376, 99, 312, 10.5, INK)
    paragraph(c, "模型是否优于随机选客仍不确定，建议先用同样预算做小规模试点。", 376, 82, 312, 10)


def preview_customers(c, d):
    preview_slicer(c, "客户分群", [r["segment"] for r in d.segments])
    preview_panel(c, 18, 150, 385, 156, "各客群的客户占比与消费额占比")
    segment_bars(c, 27, 156, 363, 124, d.segments)
    preview_panel(c, 412, 150, 290, 156, "不同批次客户的再次购买")
    cohort = [(r[0], r[1], pct(r[3]), f"{r[4]:,}") for r in d.cohort]
    grid_table(c, 423, 278, [68, 67, 61, 72], ("分组月份", "复购月份", "复购率", "该批人数"),
               cohort, row_h=26, size=9.5, emphasis=(2,))
    preview_panel(c, 18, 31, 684, 110, "消费指标 · 支持客群筛选")
    tab = [(r["segment"], f"{int(r['customers']):,}", f"{int(r['orders']):,}",
            f"{float(r['order_weighted_aov']):.2f}", f"{float(r['median_customer_gap_days']):.0f}")
           for r in d.segments]
    grid_table(c, 29, 114, [152, 100, 104, 144, 162],
               ("客群", "客户数", "订单量", "平均每单金额", "典型购买间隔（天）"),
               tab, row_h=14, size=7.5)


def preview_experiment(c, d):
    preview_slicer(c, "分析客群", [r["segment"] for r in d.effect])
    preview_panel(c, 18, 65, 363, 241, "短信组与对照组的购买率")
    preview_panel(c, 391, 65, 311, 241, "购买率差与结果确定性")
    left, right = 95, 330
    for i in range(5):
        x = left+i*(right-left)/4
        rule(c, x, 96, x, 250)
        serif(c, f"{i * 25}%", x+9, 82, 8.5, MUTED, right=True)
    for i, (key, title, tone) in enumerate([
        ("control_rate", "对照组", GOLD), ("sms_rate", "短信组", VIOLET)
    ]):
        x = 97+i*112
        rect(c, x, 259, 8, 8, tone)
        label(c, title, x+12, 268, 91, 10, MUTED)
        for j, row in enumerate(d.effect):
            yy = 232-j*25-i*9
            val = float(row[key])
            rect(c, left, yy, val*(right-left), 6.5, tone)
            serif(c, f"{val:.1%}", left+val*(right-left)+5, yy, 8.5, INK)
            if i == 0:
                label(c, row["segment"], 29, yy+8, 65, 9, INK)
    tab = [(r["segment"], pp(r["difference_pp"]), ci(r),
            "高于对照" if (float(r["holm_p"]) < .05 if r["holm_p"] else float(r["ci_low_pp"]) > 0)
            else "尚不确定") for r in d.effect]
    grid_table(c, 401, 277, [78, 44, 105, 64],
               ("客群", "差值", "95%估计范围(pp)", "判断"), tab, row_h=27,
               size=9, emphasis=(0,))


def preview_strategy(c, d):
    preview_slicer(c, "检验阶段", ["方案筛选", "独立检验"])
    preview_panel(c, 18, 121, 342, 185, "方案筛选 · 覆盖比例与购买率差")
    coverage_chart(c, 28, 130, 319, 148, d.curves)
    preview_panel(c, 18, 31, 342, 80, "多轮比较 · 相对原选客方案")
    opt = [(PORTFOLIO_MODELS[r["model"]], pp(r["mean_vs_base_t_pp"]), r["folds_positive_vs_base_t"])
           for r in d.opt]
    grid_table(c, 29, 84, [155, 90, 74], ("模型", "平均差值 (pp)", "更好的轮次"), opt,
               row_h=13, size=6.8, emphasis=(1,))
    preview_panel(c, 370, 187, 332, 119, "覆盖 30% 客户 · 独立检验")
    tab = [(PORTFOLIO_POLICIES[r["policy"]], pp(r["uplift_pp"]), ci(r)) for r in d.hold]
    grid_table(c, 381, 278, [108, 84, 118],
               ("策略", "购买率差 (pp)", "95%估计范围(pp)"), tab, row_h=19,
               size=9.1, emphasis=(0,))
    preview_panel(c, 370, 31, 332, 147, "换用模型能改善多少")
    tab = [(name, f"{point:+.2f}", f"[{low:+.2f}, {high:+.2f}]")
           for name, point, low, high in [
               ("初筛 · 对随机", *d.paired[0][1:]),
               ("独立检验 · 对随机", *d.paired[1][1:]),
               ("独立检验 · 对历史价值", *d.paired[2][1:])]]
    grid_table(c, 381, 149, [131, 61, 118], ("检验阶段与对比方案", "差值", "95%估计范围(pp)"), tab,
               row_h=24, size=9.4, emphasis=(1,))


def dashboard_spread(c, number, title, deck, page_title, insights, draw, d, total):
    frame(c, f"POWER BI  /  0{number}", title, deck)
    x, y, w = 42, 61, 701
    c.saveState()
    c.translate(x, y)
    c.scale(w/720, w/720)
    rect(c, 0, 0, 720, 405, LILAC)
    rect(c, 18, 360, 684, 32, DEEP)
    rect(c, 18, 360, 4, 32, GOLD)
    label(c, f"0{number}  {page_title}", 29, 386, 650, 15, white)
    draw(c, d)
    c.restoreState()
    rule(c, 758, 66, 758, 454, GRID)
    yy = 429
    for head, body in insights:
        label(c, head, 777, yy, 138, 12, VIOLET)
        yy = paragraph(c, body, 777, yy-23, 139, 11.5) - 24
    portfolio_footer(c, number+2, total)


def portfolio(path, d):
    c = Canvas(str(path), pagesize=(W, H), pageCompression=1)
    c._x5_portfolio = True
    c.setTitle("X5 RetailHero 零售客户分析与短信营销效果评估")
    c.setSubject("零售客户行为、实验评估与 Power BI")
    n = 8

    rect(c, 0, 0, W, H, DEEP)
    rect(c, 598, 0, 362, H, PLUM)
    rings(c, 787, 402, 222, 11)
    circle(c, 787, 402, 81, GOLD)
    serif(c, "X5", 738, 373, 61, DEEP)
    label(c, "RETAIL ANALYTICS  /  CASE STUDY", 43, 553, 550, 13, GOLD)
    serif(c, "RetailHero", 42, 413, 88, white)
    label(c, "零售客户分析与", 44, 359, 505, 37, white)
    label(c, "短信营销效果评估", 44, 306, 505, 37, white)
    paragraph(c, "分析客户消费贡献、比较短信营销效果，为有限预算下的客户选择和投放试点提供依据。", 47, 208, 466, 16, LILAC)
    rule(c, 635, 211, 919, color=SMOKE)
    serif(c, "45.79M", 635, 155, 51, GOLD)
    label(c, "商品交易明细", 637, 141, 256, 13, LILAC)
    portfolio_footer(c, 1, n, dark=True)

    frame(c, "RESEARCH DESIGN", "项目流程与主要结果",
          "围绕客户维护和营销预算，依次判断哪些客户贡献较多、短信组购买率是否更高，以及选客方式是否值得推广。")
    rect(c, 42, 288, 876, 132, DEEP)
    flow_steps(c, 68, 333, 834, [("核对记录", "统一消费口径"), ("识别客群", "了解购买习惯"), ("比较购买", "短信组与对照组"), ("制定方案", "按预算选择客户"), ("独立检验", "检查推广依据"), ("优化与交付", "形成试点建议")], True)
    pieces = [
        ("客户行为", pct(d.overview[6]), "高价值客户占比",
         f"贡献 {pct(d.overview[7])} 的历史消费额，适合优先安排客户维护资源。"),
        ("短信活动", pp(d.overview[4]), "购买率差 · 百分点",
         "短信组 63.65%，对照组 60.33%。可继续试验，但需核实分组方式和实际投放成本。"),
        ("排序策略", pp(d.overview[5]), "独立检验 · 比随机选客高",
         "换一批客户后，模型是否更好仍不确定。建议先做同预算试点，再决定扩大投放。"),
    ]
    for i, (section, value, metric, copy) in enumerate(pieces):
        xx = 42+295*i
        rect(c, xx, 70, 286, 192, (LILAC, white, PALE)[i])
        label(c, section, xx+15, 247, 250, 13, INK)
        serif(c, value, xx+15, 178, 41, VIOLET)
        label(c, metric, xx+16, 163, 248, 10, MUTED)
        paragraph(c, copy, xx+15, 133, 255, 11.5)
    portfolio_footer(c, 2, n)

    dashboard_spread(c, 1, "项目结果概览",
                     "集中查看客户消费贡献、短信购买率差和当前投放建议，为预算讨论提供依据。",
                     "决策总览",
                     [("活动效果", "短信活动整体购买率差为 +3.32 个百分点。"),
                      ("排序效果", "换一批客户后仅高出 0.29 个百分点，优势仍不确定，建议先试点。")],
                     preview_overview, d, n)
    dashboard_spread(c, 2, "客户分层与复购分析",
                     "按客群查看消费贡献和购买习惯，识别重点维护对象及购买放缓的客户。",
                     "客户行为",
                     [("看分群", "高价值客户占 15.1%，贡献 37.3% 的历史消费额。"),
                      ("看复购", "1 月首次观察到的客户中，有 85.6% 在 2 月再次购买。")],
                     preview_customers, d, n)
    dashboard_spread(c, 3, "短信营销效果分析",
                     "比较短信组与对照组的购买情况。估计范围越宽，结果越不确定，投放决策还需考虑成本。",
                     "短信活动",
                     [("总体效果", "短信组 63.65%，对照组 60.33%。"),
                      ("召回假设", "尚不能确定待唤醒客户的短信效果更好，可把这一客群纳入下一轮试点。")],
                     preview_experiment, d, n)
    dashboard_spread(c, 4, "客户排序策略比较",
                     "预算只能覆盖 30% 客户时，比较模型选客、随机选客和按历史消费价值选客的效果。",
                     "排序验证",
                     [("推广依据", "初步筛选时高出 3.45 个百分点，换一批客户后仅高出 0.29 个百分点，优势仍需验证。"),
                      ("预算口径", "各方案均覆盖 30% 客户，比较同等触达规模下能否增加购买。")],
                     preview_strategy, d, n)

    frame(c, "MODEL OPTIMIZATION", "模型优化结果",
          "加入客户购买节奏和近期订单变化，检验选客效果是否改善。共比较 15 轮，每轮覆盖 30% 客户，差值单位为百分点。")
    optimization_rows = [
        (PORTFOLIO_MODELS[r["model"]], pp(r["mean_uplift_pp"]), pp(r["mean_vs_random_pp"]),
         pp(r["mean_vs_base_t_pp"]),
         "—" if r["model"] == "base_t" else r["folds_positive_vs_base_t"] + " / 15")
        for r in d.opt
    ]
    grid_table(c, 42, 433, [240, 170, 150, 150, 166],
               ("方案", "平均购买率差", "领先随机选客", "领先原方案", "优于原方案的轮次"),
               optimization_rows, row_h=39, size=12, emphasis=(1,))
    label(c, "增强方案的三次重复结果", 42, 255, 425, 16, INK)
    label(c, "相对原方案的平均差值（百分点）", 42, 230, 425, 11, MUTED)
    repeats = rows("07_uplift_optimization", "repeat_summary")
    enhanced = sorted((r for r in repeats if r["model"] == "behavior_t"),
                      key=lambda r: int(r["repeat"]))
    zero, scale = 241, 641
    rule(c, zero, 79, zero, 208, color=MUTED, dashed=True)
    for i, result in enumerate(enhanced):
        value = float(result["vs_base_t_pp"])
        y = 187 - i * 43
        label(c, f"第 {i+1} 次", 43, y+8, 72, 11, MUTED)
        rect(c, zero+min(value, 0)*scale, y-6, abs(value)*scale, 13,
             VIOLET if value > 0 else OCHRE)
        value_x = zero+value*scale+8 if value > 0 else zero+8
        serif(c, f"{value:+.3f}", value_x, y-4, 12, INK)
    label(c, "业务结论", 511, 255, 407, 17, VIOLET)
    paragraph(c, "增加客户行为信息后，平均只改善 0.02 个百分点，收益幅度有限。多轮比较也有起伏，当前继续使用原方案，待试点支持后再考虑更换。", 
              511, 222, 407, 13)
    paragraph(c, "建议先用同样预算开展投放试点，核对额外购买和扣除成本后的收益，再决定是否继续投入优化。多轮比较有部分客户重复参与，还需用新客户验证。",
              511, 127, 407, 12, MUTED)
    portfolio_footer(c, 7, n)

    rect(c, 0, 0, W, H, DEEP)
    rect(c, 626, 0, 334, H, PLUM)
    label(c, "DECISION  /  NEXT EXPERIMENT", 44, 544, 560, 12, GOLD)
    label(c, "研究结论与", 44, 486, 550, 38, white)
    label(c, "后续试点建议", 44, 432, 552, 38, white)
    paragraph(c, "从同一批客户中随机分组，分别用两种方式选客。", 47, 360, 491, 18, LILAC)
    paragraph(c, "两组都覆盖 30% 客户，统一短信内容和优惠。", 47, 330, 491, 18, LILAC)
    paragraph(c, "比较整组购买率和净收益，再决定是否扩大投放。", 47, 300, 491, 18, LILAC)
    flow_steps(c, 51, 221, 546, [("分组试点", "同一批合格客户"),
                                ("同预算投放", "统一内容与优惠"),
                                ("复核收益", "购买改善与成本")], True)
    label(c, "继续保留原方案", 649, 469, 270, 17, white)
    serif(c, "+0.02", 648, 367, 67, GOLD)
    paragraph(c, "百分点 · 增加客户行为信息后的平均改善，现阶段不足以支持更换方案。", 651, 335, 254, 14, LILAC)
    rule(c, 650, 252, 900, color=SMOKE)
    serif(c, "200,123", 649, 187, 39, GOLD)
    paragraph(c, "位待评客户已形成选客参考分数，实际购买结果仍待验证。", 651, 165, 259, 13, LILAC)
    portfolio_footer(c, 8, n, dark=True)
    c.save()


def workflow(path, d):
    width, height = 760, 1450
    c = Canvas(str(path), pagesize=(width, height), pageCompression=1)
    rect(c, 0, 0, width, height, PAPER)
    rect(c, 0, height-318, width, 318, DEEP)
    rings(c, 670, 1310, 193, 9)
    circle(c, 668, 1310, 49, GOLD)
    serif(c, "X5", 640, 1295, 32, DEEP)
    label(c, "RETAILHERO  /  ANALYSIS WORKFLOW", 43, 1400, 590, 12, GOLD)
    label(c, "零售营销增量", 42, 1352, 563, 42, white)
    label(c, "研究流程与决策", 42, 1294, 573, 42, white)
    paragraph(c, "用交易、实验标签和独立样本，逐步验证客户选择策略。", 44, 1213, 575, 14, LILAC)
    stages = [
        ("01", "数据审计", "45,786,568 条商品明细 → 8,045,229 笔订单。使用客户与交易组合键，按处理与购买结果固定三组样本。", "120,022 / 40,008 / 40,009"),
        ("02", "客户行为", "以近度、频次与消费额识别高价值活跃和待唤醒群。计算复购间隔、同群复购和匿名品类偏好。", "15.1% 客户 · 37.3% 消费额"),
        ("03", "短信活动", "对照购买率 60.33%，短信组 63.65%。逐项报告区间与 Holm 校正，并检查高价值两群的直接差异。", "+3.32 pp · 95% CI [+2.77, +3.87]"),
        ("04", "验证与选型", "训练多种排序方法。在验证集固定 30% 触达，对比 T-Learner、随机、RFM 与其他候选。", "验证集 · 模型对随机 +3.45 pp"),
        ("05", "独立保留评价", "冻结模型和门槛。模型相对 RFM 的配对区间在零上，相对随机排序的配对区间跨零。", "模型对随机 +0.29 pp · [-1.78, +2.37]"),
        ("06", "离线交付与优化", "官方待评客户生成 200,123 条分数。增强模型平均仅领先原模型 0.02 个百分点，保留原候选。", "下一步 · 设计同预算随机试点"),
    ]
    rule(c, 63, 1102, 63, 200, color=SMOKE, weight=1)
    for i, (num, title, copy, evidence) in enumerate(stages):
        top = 1089-i*139
        rect(c, 105, top-113, 612, 120, white if i%2==0 else LILAC)
        circle(c, 63, top-23, 21, GOLD if i in (0,4,5) else VIOLET)
        serif(c, num, 51, top-29, 17, INK if i in (0,4,5) else white)
        label(c, title, 122, top-8, 555, 16, INK)
        paragraph(c, copy, 122, top-39, 568, 12, INK)
        label(c, evidence, 122, top-84, 568, 10.5, VIOLET)
    rect(c, 42, 51, 675, 161, DEEP)
    label(c, "POWER BI  /  配套面板", 61, 189, 583, 14, GOLD)
    paragraph(c, "决策总览、客户行为、短信活动、排序验证", 61, 152, 634, 14, white)
    paragraph(c, "历史活动的购买率差、模型的排序表现和正式投放前的证据门槛，分别对应三个管理层问题。", 61, 113, 627, 12.5, LILAC)
    c.showPage()
    c.save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-pdf", type=Path, required=True)
    parser.add_argument("--destination", type=Path, default=DEST)
    args = parser.parse_args()
    fonts()
    data = Results()
    args.destination.mkdir(parents=True, exist_ok=True)
    enterprise(args.destination / "X5_RetailHero_企业决策报告.pdf", data)
    portfolio(args.destination / "X5_RetailHero_数据分析作品集.pdf", data)
    workflow(args.workflow_pdf, data)


if __name__ == "__main__":
    main()
