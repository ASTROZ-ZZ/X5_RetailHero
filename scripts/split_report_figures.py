#!/usr/bin/env python3
"""Split eight selected composite figures without rebuilding the report."""
import argparse
from copy import deepcopy
from pathlib import Path
from io import BytesIO
import re

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.colors import HexColor, white
import expand_report_results as chart
from build_report_word import fonts, raster, insert_image

TARGETS = {
 1: (chart.audit,(286,125),[
   ('数据质量检查与业务处理要点','图中为月度商品明细量，单位为百万条。11 月和 3 月只覆盖部分月份，不能直接比较整月增长。客户性别未明确占 46.4%，首次兑换日期缺失 8.86%，商品品牌缺失 12.08%，购买表兑换金额字段缺失 93.35%。这些缺失可能包含业务结构性原因，需结合字段定义使用。')]),
 3: (chart.customer,None,[
   ('客户消费与购买习惯的分布','四分位数和中位数用于描述客户分布。前 10% 门槛表示约一成客户达到或超过该水平；金额沿用源数据单位。'),
   ('各客群的规模、客单价与复购间隔','客单价为订单加权均值，复购间隔先按客户计算中位数，再在客群内汇总。可计算间隔的客户共 117,607 位，另有 2,415 位因不同购买日期不足而留空；训练集总消费额为 1,033,847,003.72。')]),
 4: (chart.cohort,(180,238),[
   ('各首次观察月份的客户规模与复购情况','第 0 月为首次观察购买月。热力图中的横线包含部分月份与窗口外月份，整月复购率留空，不能据此判断流失；首次观察月份也不代表入会月份。')]),
 5: (chart.category,(20,160),[
   ('主要匿名品类的购买结构','明细占比按购买行数计算，数量占比只使用正数量，客户覆盖率为购买过该品类的客户比例。热力图品类 1—6 对应本表顺序。训练明细中有 809,502 条零数量记录，占 5.90%，参与出现频次统计，数量贡献为零。')]),
 7: (chart.experiment,(225,190),[
   ('各客群的样本规模与购买率','图中数值衡量两组历史特征差异，越接近零表示越相似，最大为 0.011。表中的 p 值经过 Holm 校正，以降低同时比较多个客群时偶然发现差异的风险；分组协议仍需核实。')]),
 9: (chart.validation,(185,225),[
   ('候选方案相对三条基准的直接比较','曲线纵轴是名单内短信与对照购买率差，单位为百分点，按每 5% 覆盖比例采样。表中的区间考虑名单重叠；同一验证集参与了选型，结果用于探索，正式采用仍需独立检验。')]),
 11: (chart.holdout,(184,220),[
   ('预留客户中模型相对基准的直接比较','每种方案均选前 12,002 位。模型、随机和 RFM 名单的短信人数分别为 5,954、6,083、6,002，对照人数分别为 6,048、5,919、6,000。高自然购买率还需与短信带来的提升结合判断；模型相对随机的差异区间仍含零。')]),
 12: (chart.optimization,(202,215),[
   ('三次重复检验相对原方案的平均差值','散点图横轴为 15 轮检验，纵轴为领先原方案的百分点，零线上方表示该轮更好。表中每次结果为该次 5 折平均，单位为百分点；重复轮次共享部分样本。随机基线每折取 12 个固定种子的平均，共保留 180 组结果。')]),
 13: (chart.delivery,(188,220),[
   ('评分名单的交付检查与排序概况','分布图横轴为预计购买概率提升，纵轴为客户数，k 表示千人。表中前 30% 为按本地向下取整规则计算的名单规模。分数是模型估计，官方测试结果尚未公开，分布与文件检查不能替代实际投放评价。')]),
}

def collect(draw):
    captured=[]
    original=chart.table
    chart.table=lambda c,top,heads,body,widths,**kwargs:captured.append((heads,body,widths))
    try: draw(Canvas(BytesIO(),pagesize=(467,442)),467,442)
    finally:chart.table=original
    return captured

def graphic(draw,box):
    low,height=box
    def paint(c,w,h):
        if draw is chart.cohort:
            records=chart.rows('02_customer_analysis','cohort_repeat')
            months=list(dict.fromkeys(r['cohort_month'] for r in records))
            for i,name in enumerate(['当月','次月','2 个月后','3 个月后','4 个月后']):
                chart.label(c,name,103+i*70,225,67,10,chart.GRAY)
            for j,month in enumerate(months):
                yy=174-j*35
                chart.label(c,month,0,yy+24,93,10,chart.GRAY)
                for i,r in enumerate([x for x in records if x['cohort_month']==month]):
                    value=float(r['repeat_rate']) if r['status']=='complete' and r['repeat_rate'] else None
                    fill=chart.LILAC if value is None else chart.PURPLE if value>.85 else HexColor('#A58BCB')
                    xx=103+i*70
                    chart.rect(c,xx,yy,67,32,fill)
                    chart.label(c,'—' if value is None else f'{value:.1%}',xx+8,yy+24,57,11,chart.GRAY if value is None else white)
            return
        old_table,old_heading,old_txt=chart.table,chart.heading,chart.txt
        chart.table=lambda *a,**k:None
        chart.heading=lambda *a,**k:None
        chart.txt=lambda *a,**k:None
        try:
            c.saveState();c.translate(0,-low);draw(c,467,442);c.restoreState()
        finally:chart.table,chart.heading,chart.txt=old_table,old_heading,old_txt
    return raster(467,height,paint)

def paragraph(doc,value,style):
    p=doc.add_paragraph(value,style=style)
    return p

def table(doc,heads,rows,widths):
    template=doc.tables[0]
    t=doc.add_table(rows=0,cols=len(heads))
    t._tbl.replace(t._tbl.tblPr,deepcopy(template._tbl.tblPr))
    t.autofit=False
    for col,width in zip(t.columns,widths):
        col.width=Pt(width)
    for i,values in enumerate([heads]+rows):
        sample=template.rows[0 if i==0 else 1 if i%2 else 2]
        row=OxmlElement('w:tr')
        if sample._tr.trPr is not None:
            row.append(deepcopy(sample._tr.trPr))
        for j,(value,width) in enumerate(zip(values,widths)):
            cell=deepcopy(sample.cells[min(j,len(sample.cells)-1)]._tc)
            leaves=cell.xpath('.//w:t')
            assert leaves
            leaves[0].text=str(value)
            for leaf in leaves[1:]:
                leaf.text=''
            cell.get_or_add_tcPr().get_or_add_tcW().set(qn('w:w'),str(round(width*20)))
            row.append(cell)
        t._tbl.append(row)
    return t

def modify(source,output,figures):
    fonts();doc=Document(source)
    chosen=[]
    for p in doc.paragraphs:
        if p.style.name=='Caption':
            m=re.match(r'图\s*(\d+)',p.text)
            if m and int(m[1]) in figures:chosen.append((int(m[1]),p))
    assert len(chosen)==len(figures)
    for number,cap in chosen:
        draw,box,descriptions=TARGETS[number]
        picture=cap._p.getnext()
        assert picture.xpath('.//w:drawing'),f'Missing picture at {number}'
        data=collect(draw);assert len(data)==len(descriptions)
        new=[]
        if box is not None and number!=5:
            new.append(deepcopy(cap._p))
            pic=paragraph(doc,'','Figure')
            insert_image(pic,graphic(draw,box),467,cap.text)
            new.append(pic._p)
        for j,((heads,records,widths),(title,explanation)) in enumerate(zip(data,descriptions),1):
            p=paragraph(doc,f'表 {number}{chr(64+j)} {title}','Table Caption')
            new.append(p._p)
            new.append(table(doc,heads,records,widths)._tbl)
            if number==5:
                # Place the heatmap next to its category lookup table.
                new.append(deepcopy(cap._p))
                pic=paragraph(doc,'','Figure')
                insert_image(pic,graphic(draw,box),467,cap.text)
                new.append(pic._p)
            p=paragraph(doc,explanation,'Normal')
            new.append(p._p)
        for node in new:cap._p.addprevious(node)
        cap._p.getparent().remove(cap._p)
        picture.getparent().remove(picture)
    output.parent.mkdir(parents=True,exist_ok=True);doc.save(output)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--figures',type=int,nargs='+',default=[3,4,5,7,9,11,12,13])
    a=p.parse_args();modify(a.source,a.output,set(a.figures))
