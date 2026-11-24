#!/usr/bin/env python3
"""Append nine business-facing results pages to the user-formatted report."""
import argparse
import csv
from copy import deepcopy
from io import BytesIO
from pathlib import Path
import re

import numpy as np
from docx import Document
from docx.shared import Pt
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from reportlab.lib.colors import HexColor, white

from build_powerbi_report import ROOT, LABELS, rows, metadata
from build_reporting_pdfs import fonts, paragraph, label, serif, rect, rule, circle, grid_table, forest
from build_report_word import raster, insert_image

PURPLE, GOLD, LILAC, GRAY = map(HexColor, ['#5A36A3','#DBB636','#E9E2F4','#6F6679'])
WIDTH, HEIGHT = 467, 442
RESULTS = ROOT/'results'


def txt(c,s,x,y,w=WIDTH,size=10):
    return paragraph(c,s,x,y,w,size)


def heading(c,s,y=432):
    label(c,s,3,y,WIDTH-6,12,PURPLE)


def bars(c,names,values,x,y,w,h,fmt='{:.1f}',color=PURPLE):
    left=x+112
    maximum=max(values)*1.19 or 1
    step=h/len(values)
    for i,(name,v) in enumerate(zip(names,values)):
        top=y+h-(i+.5)*step
        label(c,name,x,top+6,108,8.5,GRAY)
        rect(c,left,top-4,(w-160)*v/maximum,min(10,step*.42),color)
        serif(c,fmt.format(v),left+(w-160)*v/maximum+5,top-3,9,GRAY)


def table(c,top,heads,body,widths,size=9,row=25):
    grid_table(c,0,top,widths,heads,body,row_h=row,size=size)


def audit(c,w,h):
    heading(c,'全量记录覆盖与质量提示')
    monthly=rows('01_data_audit','monthly_purchase_rows')
    bars(c,[r['month'] for r in monthly],[int(r['purchase_rows'])/1e6 for r in monthly],0,292,w,106,fmt='{:.2f}')
    txt(c,'月度商品明细量，单位为百万条。11 月和 3 月为部分月份，不能直接比较整月增长。',0,279,w,9)
    table(c,245,['检查结果','记录数','业务处理要点'],[
        ['客户年龄超出 0—100','1,145','只作异常提示，年龄不用于本次选客'],
        ['数量不大于零的明细','2,707,278','保留并核对，品类数量使用正数量'],
        ['交易编号跨客户复用','28','按客户加交易编号还原订单'],
        ['首次兑换晚于历史窗口','44,953','避免把窗口后信息用于历史选客'],
        ['兑换日期早于发卡日期','536','提示时间记录存在异常'],
    ],[156,78,233],size=8.4,row=29)
    g=rows('01_data_audit','gender_counts')
    total=sum(int(r['rows']) for r in g)
    data={r['gender']:int(r['rows']) for r in g}
    txt(c,f"客户性别未明确占 {data['U']/total:.1%}。首次兑换日期缺失 8.86%，商品品牌缺失 12.08%，购买表兑换金额字段缺失 93.35%。这些缺失可能包含业务结构性原因，需按字段口径使用。",0,57,w,9)


def customer(c,w,h):
    heading(c,'客户消费与购买习惯的分布')
    labels=['距末次购买（天）','历史订单量（笔）','累计消费（源单位）','个人平均客单价','历史购买天数','个人复购间隔（天）']
    dist=rows('02_customer_analysis','customer_metric_distribution')
    table(c,404,['指标','较低四分位','中位数','较高四分位','前 10% 门槛'],[
        [name,*[f"{float(r[k]):,.2f}" for k in ['25%','50%','75%','90%']]] for name,r in zip(labels,dist)
    ],[143,81,81,81,81],size=8.6,row=29)
    txt(c,'表中中位数代表典型客户的位置，前 10% 门槛表示约一成客户达到或超过的水平；金额保留源数据单位。',0,188,w,9)
    heading(c,'五类客户的规模与消费方式',150)
    seg=rows('02_customer_analysis','segment_summary')
    table(c,128,['客群','客户数','订单均价','购买间隔中位数'],[
        [r['segment'],f"{int(r['customers']):,}",f"{float(r['order_weighted_aov']):.2f}",f"{float(r['median_customer_gap_days']):g} 天"] for r in seg
    ],[146,98,105,118],size=9,row=19)
    txt(c,'复购间隔可计算的客户为 117,607 位，另有 2,415 位因不同购买日期不足而留空。训练集总消费额为 1,033,847,003.72。',0,13,w,8)


def cohort(c,w,h):
    heading(c,'不同首次观察月份客户的后续购买')
    data=rows('02_customer_analysis','cohort_repeat')
    months=list(dict.fromkeys(r['cohort_month'] for r in data))
    left,top,cw,ch=103,373,70,45
    for i in range(5): label(c,f'第 {i} 月',left+i*cw,405,cw,10,GRAY)
    for j,month in enumerate(months):
        label(c,month,0,top-j*ch+24,90,10,GRAY)
        group=[r for r in data if r['cohort_month']==month]
        for i,r in enumerate(group):
            xx,yy=left+i*cw,top-j*ch
            good=r['status']=='complete' and bool(r['repeat_rate'])
            value=float(r['repeat_rate']) if good else None
            fill=HexColor('#F1EDF6') if not good else HexColor('#5A36A3') if value>.85 else HexColor('#A58BCB')
            rect(c,xx,yy,cw-3,ch-3,fill)
            label(c,f'{value:.1%}' if good else '—',xx+8,yy+27,cw-10,11,white if good else GRAY)
    txt(c,'第 0 月是首次观察购买的月份，自然为 100%。横线格包括部分月份与尚未观察到的月份，不发布整月复购率。',0,159,w,9)
    table(c,116,['首次观察月份','该批客户数','完整后续月份的复购率'],[
        ['2018-11','67,114','首次月份不完整'],
        ['2018-12','34,371','次月 82.8%，第二个月 88.1%'],
        ['2019-01','8,461','次月 85.6%'],
        ['2019-02','6,505','后续 3 月记录不完整'],
        ['2019-03','3,571','首次月份不完整'],
    ],[130,100,237],size=8.5,row=17)


def category(c,w,h):
    heading(c,'主要品类的购买结构与客群差异')
    data=rows('02_customer_analysis','category_preferences')
    overall=[r for r in data if r['segment']=='全部训练客户']
    top=sorted(overall,key=lambda r:float(r['line_share']),reverse=True)[:6]
    names=[r['level_2'] for r in top]
    table(c,404,['匿名二级品类','明细占比','正数量占比','购买客户覆盖率'],[
        [r['level_2'],f"{float(r['line_share']):.1%}",f"{float(r['quantity_share']):.1%}",f"{int(r['customers_with_category'])/int(r['customers_in_segment']):.1%}"] for r in top
    ],[148,90,105,124],size=9,row=25)
    heading(c,'主要品类在各客群中的明细占比',202)
    groups=[r['segment'] for r in rows('02_customer_analysis','segment_summary')]
    labels=['品类 '+str(i+1) for i in range(6)]
    for i,s in enumerate(labels): label(c,s,103+i*60,169,58,9,GRAY)
    for j,g in enumerate(groups):
        label(c,g,0,143-j*24,103,9,GRAY)
        for i,n in enumerate(names):
            r=next(q for q in data if q['segment']==g and q['level_2']==n)
            v=float(r['line_share']); xx,yy=103+i*60,123-j*24
            rect(c,xx,yy,57,22,LILAC if v<.13 else PURPLE)
            label(c,f'{v:.1%}',xx+7,yy+17,51,8.5,GRAY if v<.13 else white)
    txt(c,'品类 1—6 对应上表顺序。零数量明细共 809,502 条，占训练明细 5.90%，参与出现频次统计，数量贡献为零。',0,12,w,8)


def experiment(c,w,h):
    heading(c,'短信组与对照组的历史行为是否接近')
    b=rows('03_sms_experiment','covariate_balance')
    bars(c,[r['label'] for r in b],[float(r['absolute_smd']) for r in b],0,227,w,174,fmt='{:.4f}')
    txt(c,'图中为历史特征差异的标准化值，越小表示越接近。最大值 0.011。平衡诊断仍需配合实际分组协议核查。',0,217,w,8.5)
    heading(c,'各客群的样本规模与购买率',179)
    e=rows('03_sms_experiment','purchase_rate_effects')
    table(c,157,['客群','对照人数','短信人数','对照购买率','短信购买率','校正后 p'],[
        [r['segment'],f"{int(r['control_n']):,}",f"{int(r['sms_n']):,}",f"{float(r['control_rate']):.2%}",f"{float(r['sms_rate']):.2%}",'—' if not r['holm_p'] else '<0.001' if float(r['holm_p'])<.001 else f"{float(r['holm_p']):.3f}"] for r in e
    ],[119,68,68,75,75,62],size=8.1,row=19)
    txt(c,'校正后 p 值用于减少同时比较多个客群产生的偶然差异；越小代表证据越强，实际投放还需看效果大小与成本。',0,15,w,8)


def validation(c,w,h):
    heading(c,'六种排序方式在不同覆盖比例下的表现')
    curves=rows('04_uplift_baselines','validation_curves')
    palette=[PURPLE,GOLD,HexColor('#A58BCB'),HexColor('#437D89'),HexColor('#A76B47'),GRAY]
    policies=list(dict.fromkeys(r['policy'] for r in curves))
    left,bottom,plotw,ploth=37,207,413,151
    vals=[float(r['uplift_pp']) for r in curves]
    lo,hi=min(-2,min(vals)-.5),max(vals)+1
    for tick in [0,3,6,9]:
        yy=bottom+(tick-lo)/(hi-lo)*ploth
        rule(c,left,yy,left+plotw)
        serif(c,tick,25,yy-3,9,GRAY,right=True)
    for i,p in enumerate(policies):
        group=sorted([r for r in curves if r['policy']==p],key=lambda r:int(r['reach_pct']))
        path=c.beginPath()
        for j,r in enumerate(group):
            x=left+float(r['reach_pct'])/100*plotw;y=bottom+(float(r['uplift_pp'])-lo)/(hi-lo)*ploth
            path.moveTo(x,y) if j==0 else path.lineTo(x,y)
        c.setStrokeColor(palette[i]);c.setLineWidth(1.3);c.drawPath(path)
        x=5+i%2*239; y=395-i//2*15
        rect(c,x,y-7,11,3,palette[i]);label(c,LABELS[p],x+16,y,219,9,GRAY)
    for q in [.05,.3,.5,.75,1]: serif(c,f'{q:.0%}',left+q*plotw,191,9,GRAY)
    txt(c,'纵轴为名单内短信组与对照组购买率差，单位为百分点。曲线使用每 5% 的覆盖比例采样。',0,173,w,8.5)
    pairs=rows('04_uplift_baselines','candidate_vs_baselines')
    table(c,136,['候选相对基准','领先（百分点）','95% 区间','名单重叠'],[
        [LABELS[r['comparator']],f"{float(r['difference_pp']):+.2f}",f"[{float(r['ci_low_pp']):+.2f}, {float(r['ci_high_pp']):+.2f}]",f"{float(r['overlap_pct']):.1f}%"] for r in pairs
    ],[154,106,126,81],size=9,row=24)
    txt(c,'候选在本批数据上同时完成筛选与比较，这些区间用于探索，最终采用仍以预留客户的检验为依据。',0,24,w,9)


def holdout(c,w,h):
    heading(c,'各选客方式选中的是怎样的客户')
    hold=rows('05_holdout_evaluation','holdout_at30')
    for j,r in enumerate(hold):
        top=382-j*77
        label(c,LABELS[r['policy']],0,top,125,11,PURPLE)
        for k,(key,name,color) in enumerate([('control_rate','对照组',GOLD),('sms_rate','短信组',PURPLE)]):
            y=top-23-k*18
            v=float(r[key])
            label(c,name,124,y+7,62,9,GRAY)
            rect(c,184,y,220*v,10,color)
            serif(c,f'{v:.2%}',184+220*v+5,y,10,GRAY)
    txt(c,'RFM 选中的客户在未收到短信时也有很高购买率。经营上需要比较短信带来的提升，避免仅按客户本来就会购买的概率选客。',0,158,w,9)
    pairs=rows('05_holdout_evaluation','holdout_candidate_vs_baselines')
    table(c,112,['模型相对基准','领先（百分点）','95% 区间','名单重叠'],[
        [LABELS[r['comparator']],f"{float(r['difference_pp']):+.2f}",f"[{float(r['ci_low_pp']):+.2f}, {float(r['ci_high_pp']):+.2f}]",f"{float(r['overlap_pct']):.1f}%"] for r in pairs
    ],[154,106,126,81],size=9,row=24)
    txt(c,'三种策略各选 12,002 人。各名单的短信人数分别为 5,954、6,083、6,002；对照人数分别为 6,048、5,919、6,000。',0,23,w,8.5)


def optimization(c,w,h):
    heading(c,'逐轮检验增强方案是否持续改善')
    folds=rows('07_uplift_optimization','fold_metrics')
    left,bottom,plotw,ploth=33,224,418,142
    v=[float(r['vs_base_t_pp']) for r in folds]
    lo,hi=min(v)-.3,max(v)+.3
    for tick in [-2,-1,0,1,2]:
        if lo<=tick<=hi:
            y=bottom+(tick-lo)/(hi-lo)*ploth
            rule(c,left,y,left+plotw,color=GRAY if tick==0 else LILAC)
            serif(c,tick,24,y-3,9,GRAY,right=True)
    for model,color in [('behavior_t',PURPLE),('interaction_s',GOLD)]:
        records=[r for r in folds if r['model']==model]
        for i,r in enumerate(records):
            x=left+(i+.5)/15*plotw;y=bottom+(float(r['vs_base_t_pp'])-lo)/(hi-lo)*ploth
            circle(c,x,y,2.4,color)
    label(c,'紫色为增强 T-Learner，黄色为带交互项 S-Learner',0,406,w,10,GRAY)
    for i in [1,5,10,15]: serif(c,i,left+(i-.5)/15*plotw,207,9,GRAY)
    txt(c,'横轴为 15 轮检验，纵轴为领先原模型的百分点。零线上方表示该轮优于原模型。重复轮次共享部分样本。',0,188,w,9)
    repeats=rows('07_uplift_optimization','repeat_summary')
    table(c,142,['方案','第 1 次','第 2 次','第 3 次'],[
        [LABELS[model],*[f"{float(next(r for r in repeats if r['model']==model and r['repeat']==str(i))['vs_base_t_pp']):+.3f}" for i in range(1,4)]]
        for model in ['base_t','behavior_t','interaction_s']
    ],[185,94,94,94],size=9,row=25)
    txt(c,'每次结果为该次 5 折平均，相对原模型以百分点表示。随机基线在每折取 12 个固定种子的平均，共保留 180 组基线结果。',0,34,w,9)


def delivery(c,w,h):
    heading(c,'官方待评客户的预计提升分数分布')
    with (RESULTS/'06_offline_delivery/tables/uplift_submission.csv').open(encoding='utf-8-sig') as f:
        records=list(csv.DictReader(f))
    vals=np.array([float(r['uplift']) for r in records])
    hist,edges=np.histogram(vals,bins=24)
    left,bottom,plotw,ploth=43,212,406,170
    for fraction in [0, .5, 1]:
        y=bottom+fraction*ploth
        rule(c,left,y,left+plotw,color=LILAC)
        serif(c,f'{round(max(hist)*fraction)/1000:.0f}k',left-5,y-3,8,GRAY,right=True)
    for i,n in enumerate(hist):
        rect(c,left+i*plotw/24,bottom,plotw/24-2,float(n)/max(hist)*ploth,PURPLE)
    for q in [0,6,12,18,24]:
        serif(c,f'{edges[q]:.2f}',left+q*plotw/24,194,9,GRAY)
    txt(c,'横轴为预计购买概率提升，纵轴为落在相应分数范围内的客户数量。分数为模型估计，个人真实增量无法直接观察。',0,176,w,9)
    selected=int(len(vals)*.3);cutoff=float(np.sort(vals)[-selected])
    table(c,145,['交付检查与排序概况','结果'],[
        ['客户数及编号唯一数',f'{len(records):,} / {len(set(r["client_id"] for r in records)):,}'],
        ['与官方模板顺序核对','一致'],
        ['分数范围',f'{min(vals):.4f} 至 {max(vals):.4f}'],
        ['排序前 30% 的客户数',f'{selected:,}'],
        ['前 30% 的最低入选分数',f'{cutoff:.4f}'],
    ],[280,187],size=9,row=18)
    template=RESULTS.parent/'data/uplift_sample_submission.csv'
    with template.open(encoding='utf-8-sig') as f: ids=[r['client_id'] for r in csv.DictReader(f)]
    assert ids==[r['client_id'] for r in records]
    txt(c,'上述分布由已交付评分文件补充汇总。测试标签尚未公开，分数分布与文件检查不能替代真实投放效果评估。',0,28,w,8)


PAGES=[
 (1,'1.3  数据覆盖与质量检查',audit,'数据覆盖和质量提示','月度记录反映样本覆盖；涉及数量、日期和人口信息的异常，应按业务定义核查。原始记录被保留，订单识别采用组合编号。','第 01 阶段月度明细、质量检查、字段缺失与性别统计。'),
 (2,'2.3  客户消费与复购节奏',customer,'客户指标分布与分群明细','典型客户与高消费客户的差距明显。维护节奏应结合个人历史习惯，并在各客群中分别验证效果。','第 02 阶段客户指标分布、客群汇总及分析报告。'),
 (2,'2.4  完整月份的同群复购',cohort,'首次观察月份与后续购买','复购并非每月单调下降。观察窗口不完整的月份用横线表示，避免把缺少记录误判为客户流失。','第 02 阶段同群复购明细，25 个观察单元。'),
 (2,'2.5  主要品类与客群偏好',category,'主要品类份额与客群结构','购买行数、购买数量和客户覆盖回答不同问题。匿名品类的实际运营方案需补充真实品类对应关系。','第 02 阶段品类偏好汇总，展示前六大品类及全部五个客群。'),
 (3,'3.3  分组可比性与样本构成',experiment,'历史行为平衡与各客群购买率','短信组与对照组的历史行为接近，各客群规模仍有差异。样本较少的客群需结合较宽的效果区间解读。','第 03 阶段 14 项历史特征平衡检查和全部客群实验汇总。'),
 (4,'4.3  触达比例与完整方案比较',validation,'覆盖曲线与候选方案配对比较','预算覆盖比例变化时，各策略的表现也会变化。前 30% 是本项目固定比较口径，不能直接推导最优盈利预算。','第 04 阶段六种策略覆盖曲线与三项基准配对比较。'),
 (5,'5.3  选中客户的购买率结构',holdout,'各名单购买率与基准比较','高自然购买率并不保证短信提升更大。模型对随机的比较仍含零，扩大投放需要新试点。','第 05 阶段全部策略样本量、购买率与两项配对比较。'),
 (6,'6.3  优化结果的多轮稳定性',optimization,'15 轮比较及三次重复平均','增强方案平均改善小，逐轮结果有起伏。保留原模型符合当前证据，也为后续投入提供参照。','第 07 阶段 45 条模型折次结果、9 条重复汇总及 180 条随机基线。'),
 (6,'6.4  评分名单的交付检查',delivery,'交付分数分布与名单检查','分数可按预算形成优先名单。官方待评客户的表现仍待真实结果或新实验验证。','第 06 阶段 200,123 条交付评分及提交核验记录。'),
]


def set_text(p,s):
    runs=p.runs
    if runs:
        runs[0].text=s
        for r in runs[1:]:r.text=''
    else:p.add_run(s)


def build(src,out,assets):
    fonts()
    doc=Document(src)
    assert len(doc.tables)==6
    headings=[p for p in doc.paragraphs if p.style.name=='Heading 1']
    assert len(headings)==8
    anchor_map={i+1:headings[i+1] for i in range(7)}
    assets.mkdir(parents=True,exist_ok=True)
    for chapter,title,draw,caption,body,source in PAGES:
        nodes=[]
        p=doc.add_paragraph(title,style='Heading 2')
        p.paragraph_format.page_break_before=True;nodes.append(p._p)
        p=doc.add_paragraph(body,style='Normal');nodes.append(p._p)
        p=doc.add_paragraph(caption,style='Caption')
        p._p.set('data-added-figure','true');nodes.append(p._p)
        image=raster(WIDTH,HEIGHT,draw)
        imgfile=assets/(title.split()[0]+'_分析结果.png');imgfile.write_bytes(image.getvalue())
        p=doc.add_paragraph(style='Figure')
        insert_image(p,BytesIO(image.getvalue()),WIDTH,caption);nodes.append(p._p)
        p=doc.add_paragraph('资料来源  '+source,style='Exhibit Source');nodes.append(p._p)
        anchor=anchor_map[chapter]._p
        for node in nodes:anchor.addprevious(node)
    # Assign figure numbers in reading order and update references to the four original figures.
    original_map={}
    n=0
    for p in doc.paragraphs:
        if p.style.name=='Caption':
            n+=1
            if p._p.get('data-added-figure'):
                set_text(p,f'图 {n} '+p.text)
                del p._p.attrib['data-added-figure']
            else:
                match=re.match(r'图\s*(\d+)',p.text)
                if match:
                    original_map[match[1]]=str(n)
                    set_text(p,re.sub(r'^图\s*\d+',f'图 {n}',p.text))
    for p in doc.paragraphs:
        if p.style.name in ['Normal','Report Note']:
            changed=re.sub(r'图\s*(\d+)',lambda m:'图 '+original_map.get(m[1],m[1]),p.text)
            if changed!=p.text:set_text(p,changed)
    # Cache the chapter page references for readers who open Word without refreshing fields.
    starts=[1,3,7,9,11,13,16,17]
    for p in doc.paragraphs:
        if p.style.name=='Contents Chapter':
            for run in p._p.findall(qn('w:r')):
                instruction=run.find(qn('w:instrText'))
                if instruction is not None:
                    match=re.search(r'PAGEREF Chapter(\d+)',instruction.text or '')
                    if match:
                        text=run.find(qn('w:t'))
                        if text is not None:text.text=str(starts[int(match[1])-1])
    out.parent.mkdir(parents=True,exist_ok=True)
    doc.save(out)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('output',type=Path);p.add_argument('--assets',type=Path,required=True)
    a=p.parse_args();build(a.source,a.output,a.assets)
