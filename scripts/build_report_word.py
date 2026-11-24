#!/usr/bin/env python3
"""Export the enterprise report as editable Word text and tables."""

import argparse
from io import BytesIO
from pathlib import Path
import re

from docx import Document
from docx.enum.section import WD_SECTION_START
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor
import pypdfium2
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import PageBreak, Paragraph, Spacer, Table

from build_reporting_pdfs import (
    DEEP, DEST, GOLD, PLUM, REPORT_SECTIONS, SMOKE, ReportFigure, Results,
    circle, enterprise_story, fonts, rect, rings, rule, serif,
)


CONTENT_WIDTH = A4[0] - 128
TITLE = "零售客户洞察与短信增量策略评估"
INK, MUTED, PURPLE, LINE = "27183E", "61586F", "5A36A3", "D9D0E3"
BODY_CN, TITLE_CN, LATIN = "Songti SC", "Heiti SC", "Times New Roman"
PARAGRAPH_STYLES = {
    "prose": "Normal", "source": "Report Note", "table-title": "Table Caption",
}
TABLE_SOURCES = (
    "项目第 01 阶段源表审计汇总。",
    "项目第 01 阶段固定样本划分。",
    "项目第 04 阶段验证集前 30% 触达策略汇总。",
    "项目第 05 阶段独立保留集前 30% 触达策略汇总。",
    "项目第 07 阶段开发集重复交叉验证结果。",
    "项目指标字典与第 03 至 05 阶段评估口径。",
)
FIGURE_SOURCES = (
    "项目第 02 阶段客户分层汇总表。",
    "项目第 03 阶段短信营销实验分析。",
    "项目第 04 阶段验证集触达曲线。",
    "项目第 04 至 05 阶段候选模型与基线的配对比较。",
)


def element(tag, **attrs):
    node = OxmlElement("w:" + tag)
    for key, value in attrs.items():
        node.set(qn("w:" + key), str(value))
    return node


def configure_style(styles, name, size, leading, *, east_asia=BODY_CN, color=INK,
                    before=0, after=0, align=WD_ALIGN_PARAGRAPH.LEFT,
                    indent=0, keep=False, bold=False):
    style = styles[name] if name in styles else styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
    style.font.name = LATIN
    style.font.size = Pt(size)
    style.font.color.rgb = RGBColor.from_string(color)
    style.font.bold = bold
    style.font.italic = False
    props = style._element.get_or_add_rPr()
    faces = props.get_or_add_rFonts()
    for key in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme"):
        faces.attrib.pop(qn(f"w:{key}"), None)
    faces.set(qn("w:eastAsia"), east_asia)
    lang = props.find(qn("w:lang"))
    if lang is None:
        lang = element("lang")
        props.append(lang)
    lang.set(qn("w:eastAsia"), "zh-CN")

    layout = style.paragraph_format
    layout.alignment = align
    layout.first_line_indent = Pt(indent)
    layout.line_spacing = Pt(leading)
    layout.space_before = Pt(before)
    layout.space_after = Pt(after)
    layout.keep_with_next = keep
    layout.widow_control = True
    if name == "Title":
        paragraph_props = style._element.get_or_add_pPr()
        borders = paragraph_props.find(qn("w:pBdr"))
        if borders is not None:
            paragraph_props.remove(borders)
    return style


def configure_document(doc):
    doc.core_properties.title = "X5 RetailHero 企业决策报告"
    doc.core_properties.subject = TITLE
    doc.core_properties.author = ""
    doc.core_properties.comments = ""
    section = doc.sections[0]
    section.page_width, section.page_height = Mm(210), Mm(297)
    section.left_margin = section.right_margin = Pt(64)
    section.top_margin, section.bottom_margin = Pt(69), Pt(53)
    section.header_distance, section.footer_distance = Pt(28), Pt(25)
    section.different_first_page_header_footer = True

    styles = doc.styles
    center = WD_ALIGN_PARAGRAPH.CENTER
    configure_style(styles, "Normal", 11.8, 19.3, after=7, indent=23.6)
    configure_style(styles, "Title", 36, 48, east_asia=TITLE_CN, before=48, after=15, keep=True)
    configure_style(styles, "Heading 1", 19, 28, east_asia=TITLE_CN, after=14, keep=True)
    configure_style(styles, "Heading 2", 12.5, 19, east_asia=TITLE_CN, before=9, after=4, keep=True, bold=True)
    configure_style(styles, "Heading 3", 11.8, 18, east_asia=TITLE_CN, before=3, after=3, keep=True)
    configure_style(styles, "Summary Heading", 12.5, 18, east_asia=TITLE_CN, before=8, after=4, keep=True, bold=True)
    configure_style(styles, "Front Matter", 19, 28, east_asia=TITLE_CN, after=18, keep=True)
    configure_style(styles, "Caption", 10.5, 15, before=4, after=4, align=center, keep=True, bold=True, east_asia=TITLE_CN)
    configure_style(styles, "Table Caption", 10.5, 15, before=3, after=4, align=center, keep=True, bold=True, east_asia=TITLE_CN)
    configure_style(styles, "Report Note", 9.5, 14, after=6, color=MUTED)
    configure_style(styles, "Exhibit Source", 9.2, 13, before=3, after=8, color=MUTED)
    configure_style(styles, "Table Entry", 10.8, 14.5)
    configure_style(styles, "Table Heading", 10.8, 15, east_asia=TITLE_CN, color="FFFFFF", bold=True)
    configure_style(styles, "Report Header", 9, 13, color=MUTED)
    configure_style(styles, "Report Footer", 10.5, 14, color=MUTED, align=center)
    configure_style(styles, "Contents Chapter", 12, 17, east_asia=TITLE_CN, before=10, after=3, keep=True)
    configure_style(styles, "Contents Topic", 10.8, 17, color=MUTED)
    decision = configure_style(styles, "Summary Decision", 12, 20, before=8, after=16)
    decision.paragraph_format.left_indent = Pt(12)
    decision.paragraph_format.right_indent = Pt(12)
    figure = configure_style(styles, "Figure", 10, 14, align=center, keep=True)
    figure.paragraph_format.line_spacing = 1.0
    cover_graphic = configure_style(styles, "Cover Graphic", 10, 14, align=center)
    cover_graphic.paragraph_format.line_spacing = 1.0
    configure_style(styles, "Cover Series", 13, 21, east_asia=TITLE_CN, color=PURPLE, bold=True, keep=True)
    configure_style(styles, "Cover Subtitle", 14, 22, color=MUTED, after=29, keep=True)
    configure_style(styles, "Cover Topics", 10.5, 18, color=MUTED, before=16)
    report_header(section.header.paragraphs[0])


def report_header(header, *, chapter=False):
    header.style = "Report Header"
    marker = header.add_run("━  ")
    marker.font.color.rgb = RGBColor.from_string("BF941F")
    header.add_run("X5 RetailHero  /  企业决策报告")
    if chapter:
        header.paragraph_format.tab_stops.add_tab_stop(Pt(CONTENT_WIDTH), WD_TAB_ALIGNMENT.RIGHT)
        header.add_run("\t")
        field(header, 'STYLEREF "Heading 1"', REPORT_SECTIONS[0][0])
    borders = element("pBdr")
    borders.append(element("bottom", val="single", sz=4, space=5, color=LINE))
    header._p.get_or_add_pPr().append(borders)


def raster(width, height, draw):
    stream = BytesIO()
    c = Canvas(stream, pagesize=(width, height), pageCompression=1)
    draw(c, width, height)
    c.showPage()
    c.save()
    pdf = pypdfium2.PdfDocument(stream.getvalue())
    try:
        bitmap = pdf[0].render(scale=3.0)
        buffer = BytesIO()
        bitmap.to_pil().save(buffer, format="PNG")
        buffer.seek(0)
        return buffer
    finally:
        pdf.close()


def insert_image(paragraph, image, width, alt):
    inline = paragraph.add_run().add_picture(image, width=Pt(width))
    inline._inline.docPr.set("descr", alt)


def cover(doc):
    doc.add_paragraph("X5 RETAILHERO  /  零售营销研究", style="Cover Series")
    doc.add_paragraph("零售客户洞察与\n短信增量策略评估", style="Title")
    doc.add_paragraph("Retail Customer Insights and SMS Uplift Evaluation", style="Cover Subtitle")

    def draw(c, width, height):
        rect(c, 0, 0, width, height, DEEP)
        rect(c, 0, 0, width, 4, GOLD)
        for x in range(32, int(width)-25, 27):
            rule(c, x, 23, x, height-23, PLUM, .65)
        for y in range(25, int(height)-22, 27):
            rule(c, 26, y, width-26, color=PLUM, weight=.65)
        rings(c, width*.71, height*.53, 115, 8)
        circle(c, width*.71, height*.53, 48, GOLD)
        serif(c, "X5", width*.71-29, height*.53-13, 34, DEEP)
        rule(c, 35, 61, 165, color=SMOKE, weight=.5)
        serif(c, "RETAIL MARKETING STUDY", 35, 72, 9, SMOKE)

    picture = raster(CONTENT_WIDTH, 282, draw)
    insert_image(doc.add_paragraph(style="Cover Graphic"), picture, CONTENT_WIDTH, "深紫网格中的金色 X5 封面图案")
    p = doc.add_paragraph("历史交易  2018.11–2019.03", style="Cover Topics")
    p.paragraph_format.tab_stops.add_tab_stop(Pt(CONTENT_WIDTH), WD_TAB_ALIGNMENT.RIGHT)
    p.add_run("\tX5 RetailHero 公开数据案例")


def link(paragraph, text, *, target=None, anchor=None, color=PURPLE):
    hyperlink = element("hyperlink")
    if anchor is not None:
        hyperlink.set(qn("w:anchor"), anchor)
    else:
        rid = paragraph.part.relate_to(target, RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
        hyperlink.set(qn("r:id"), rid)
    run = element("r")
    props = element("rPr")
    props.append(element("color", val=color))
    run.append(props)
    t = element("t")
    t.text = text
    run.append(t)
    hyperlink.append(run)
    paragraph._p.append(hyperlink)


def field(paragraph, instruction, cached):
    run = paragraph.add_run()
    run._r.append(element("fldChar", fldCharType="begin"))
    code = element("instrText")
    code.set(qn("xml:space"), "preserve")
    code.text = " " + instruction + " "
    run._r.append(code)
    run._r.append(element("fldChar", fldCharType="separate"))
    text = element("t")
    text.text = cached
    run._r.append(text)
    run._r.append(element("fldChar", fldCharType="end"))


def executive_summary(doc, blocks):
    title = doc.add_paragraph("执行摘要", style="Front Matter")
    title.paragraph_format.page_break_before = True
    _, scope, method, experiment, validation, decision, keywords = [
        item.getPlainText() for item in blocks if isinstance(item, Paragraph)
    ]
    p = doc.add_paragraph(style="Summary Decision")
    p.add_run("投放判断  ").bold = True
    p.add_run(decision)
    props = p._p.get_or_add_pPr()
    borders = element("pBdr")
    borders.append(element("left", val="single", sz=16, space=7, color=PURPLE))
    props.append(borders)
    props.append(element("shd", fill="F5F1FB"))

    for label, paragraphs in (
        ("研究范围", (scope,)),
        ("分析路径", (method,)),
        ("主要发现", (experiment, validation)),
    ):
        doc.add_paragraph(label, style="Summary Heading")
        for value in paragraphs:
            doc.add_paragraph(value)
    doc.add_paragraph(keywords, style="Report Note")


def contents(doc):
    header = doc.add_paragraph("目录", style="Front Matter")
    header.paragraph_format.page_break_before = True
    for n, (title, subjects) in enumerate(REPORT_SECTIONS, 1):
        p = doc.add_paragraph(style="Contents Chapter")
        p.paragraph_format.tab_stops.add_tab_stop(Pt(CONTENT_WIDTH), WD_TAB_ALIGNMENT.RIGHT,
                                                   WD_TAB_LEADER.DOTS)
        anchor = f"Chapter{n}"
        link(p, title, anchor=anchor)
        p.add_run("\t")
        field(p, "PAGEREF " + anchor + " \\h", str(n))
        for i, subject in enumerate(subjects, 1):
            subsection = doc.add_paragraph(style="Contents Topic")
            subsection.paragraph_format.left_indent = Pt(16)
            link(subsection, f"{n}.{i}  {subject}", anchor=f"Subsection{n}_{i}", color=MUTED)


def start_body(doc):
    section = doc.add_section(WD_SECTION_START.NEW_PAGE)
    section.different_first_page_header_footer = False
    section.header.is_linked_to_previous = False
    section.footer.is_linked_to_previous = False
    report_header(section.header.paragraphs[0], chapter=True)
    page_num = element("pgNumType", start=1)
    section._sectPr.insert_element_before(page_num, "w:cols", "w:formProt", "w:vAlign")
    footer = section.footer.paragraphs[0]
    footer.style = "Report Footer"
    field(footer, "PAGE", "1")


def add_bookmark(paragraph, name, index):
    paragraph._p.insert(1, element("bookmarkStart", id=index, name=name))
    paragraph._p.append(element("bookmarkEnd", id=index))


def word_table(doc, flowable):
    data = flowable._cellvalues
    widths = flowable._argW
    table = doc.add_table(rows=len(data), cols=len(widths))
    table.autofit = False
    for column, width in zip(table.columns, widths):
        column.width = Pt(width)
    props = table._tbl.tblPr
    borders = element("tblBorders")
    for tag, color, size in (("top", PURPLE, 6), ("bottom", PURPLE, 6),
                             ("insideH", LINE, 3)):
        borders.append(element(tag, val="single", color=color, sz=size))
    props.append(borders)
    padding = element("tblCellMar")
    for side, amount in (("top", 66), ("bottom", 66), ("left", 116), ("right", 116)):
        padding.append(element(side, w=amount, type="dxa"))
    props.append(padding)

    for i, (row, values) in enumerate(zip(table.rows, data)):
        row_props = row._tr.get_or_add_trPr()
        row_props.append(element("cantSplit"))
        if i == 0:
            row_props.append(element("tblHeader", val="true"))
        for cell, width, value in zip(row.cells, widths, values):
            cell.width = Pt(width)
            if i == 0 or i % 2 == 0:
                cell._tc.get_or_add_tcPr().append(element("shd", fill="3B235E" if i == 0 else "F9F7FC"))
            p = cell.paragraphs[0]
            p.style = "Table Heading" if i == 0 else "Table Entry"
            p.add_run(value.getPlainText())


def build(out):
    fonts()
    source = enterprise_story(Results(), CONTENT_WIDTH)
    doc = Document()
    configure_document(doc)
    cover(doc)
    end_summary = next(i for i, block in enumerate(source[2:], 2) if isinstance(block, PageBreak))
    executive_summary(doc, source[2:end_summary])
    contents(doc)
    start_body(doc)

    first_chapter = next(i for i, block in enumerate(source) if getattr(block, "bookmark", None) == "chapter-1")
    table_number = figure_number = 0
    blocks = iter(source[first_chapter:])
    for block in blocks:
        if isinstance(block, Paragraph):
            title, style = block.getPlainText(), block.style.name
            if style == "chapter":
                chapter = int(block.bookmark.rsplit("-", 1)[1])
                p = doc.add_paragraph(title, style="Heading 1")
                p.paragraph_format.page_break_before = chapter > 1
                add_bookmark(p, f"Chapter{chapter}", chapter*10)
                continue
            if style == "topic":
                if title.startswith(("（一）", "（二）")):
                    section = "一二".index(title[1])+1
                    p = doc.add_paragraph(f"{chapter}.{section}  {title[3:]}", style="Heading 2")
                    add_bookmark(p, f"Subsection{chapter}_{section}", chapter*10+section)
                else:
                    doc.add_paragraph(title, style="Heading 3")
                continue
            if title in ("来源 项目第 02 阶段客户分层汇总表。",
                         "来源 项目第 03 阶段短信营销实验分析。"):
                continue
            p = doc.add_paragraph(style=PARAGRAPH_STYLES[style])
            url = re.search(r'<link href="([^"]+)"', block.text)
            if url:
                link(p, title, target=url[1])
            else:
                p.add_run(title)
        elif isinstance(block, ReportFigure):
            caption = next(blocks).getPlainText()
            doc.add_paragraph(caption, style="Caption")
            picture = raster(block.width, block.height, block.draw_figure)
            insert_image(doc.add_paragraph(style="Figure"), picture, block.width, caption)
            doc.add_paragraph("资料来源  " + FIGURE_SOURCES[figure_number], style="Exhibit Source")
            figure_number += 1
        elif isinstance(block, Table):
            word_table(doc, block)
            doc.add_paragraph("资料来源  " + TABLE_SOURCES[table_number], style="Exhibit Source")
            table_number += 1
        elif not isinstance(block, (PageBreak, Spacer)):
            raise TypeError(type(block).__name__)

    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEST / "X5_RetailHero_企业决策报告.docx")
    build(parser.parse_args().output)
