from pathlib import Path
import json,csv,gzip,base64,hashlib
ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'PowerBI'
REPORT=OUT/'X5RetailHero.Report'; MODEL=OUT/'X5RetailHero.SemanticModel'
def dump(p,o):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(o,ensure_ascii=False,indent=2),encoding='utf-8')
def schema(p):return 'https://developer.microsoft.com/json-schemas/'+p+'/schema.json'
def literal(s):return {'expr':{'Literal':{'Value':s}}}
def txt(s):return literal("'"+s.replace("'","''")+"'")
frames={}
for p in sorted((OUT/'data').glob('*.csv')):
 with p.open(encoding='utf-8-sig',newline='') as f:frames[p.stem]=list(csv.DictReader(f))
# Stable field types; identifiers, categories and dates are never coerced to numbers.
STRINGS={'Date','Store','Segment','cohort_month','activity_month','status','policy','label','Sample','comparator','model','CohortMonth','RecencyBand'}
tables=[]; types={}; allmeasures=[]
def addmeasure(table,name,expression,fmt='0.00'):
 next(t for t in tables if t['name']==table)['measures'].append({'name':name,'expression':expression,'formatString':fmt,'displayFolder':'业务指标'});allmeasures.append((table,name,expression,fmt))
for name,rows in frames.items():
 fields=list(rows[0]);values=[];typ={}
 for col in fields:
  nonempty=[r[col] for r in rows if r[col]!='']
  if col in STRINGS or not nonempty or any(v.lower() in ('true','false') for v in nonempty):kind='string'
  else:
   try:kind='int64' if all(float(v).is_integer() for v in nonempty) else 'double'
   except ValueError:kind='string'
  typ[col]=kind
 for r in rows:values.append([None if r[c]=='' else str(r[c]) if typ[c]=='string' else int(float(r[c])) if typ[c]=='int64' else float(r[c]) for c in fields])
 payload=base64.b64encode(gzip.compress(json.dumps(values,ensure_ascii=False,separators=(',',':')).encode(),mtime=0)).decode()
 chunks=[payload[i:i+30000] for i in range(0,len(payload),30000)]
 mtypes={'string':'type text','int64':'Int64.Type','double':'type number'}
 mfields='{'+','.join(json.dumps(c,ensure_ascii=False) for c in fields)+'}'
 m=['let','    Encoded = Text.Combine({'+','.join(json.dumps(x) for x in chunks)+'}),','    Rows = Json.Document(Binary.Decompress(Binary.FromText(Encoded, BinaryEncoding.Base64), Compression.GZip)),','    Source = Table.FromRows(Rows, '+mfields+'),','    Typed = Table.TransformColumnTypes(Source, {'+','.join('{'+json.dumps(c)+', '+mtypes[typ[c]]+'}' for c in fields)+'}, "en-US")','in','    Typed']
 tables.append({'name':name,'columns':[{'name':c,'dataType':typ[c],'sourceColumn':c,'summarizeBy':'none'} for c in fields],'measures':[],'partitions':[{'name':name,'mode':'import','source':{'type':'m','expression':m}}],'annotations':[{'name':'PBI_ResultType','value':'Table'}]})
 types[name]=typ
 (OUT/'queries').mkdir(exist_ok=True);(OUT/'queries'/f'{name}.pq').write_text('\n'.join(m))
addmeasure('Customers','客户数','SUM(Customers[Clients])','#,0')
addmeasure('Customers','历史消费额','DIVIDE(SUM(Customers[SalesCents]),100)')
addmeasure('Customers','历史订单数','SUM(Customers[Orders])','#,0')
addmeasure('Customers','客单价','DIVIDE([历史消费额],[历史订单数])')
addmeasure('Customers','客户占比',"DIVIDE([客户数],CALCULATE([客户数],REMOVEFILTERS('Segment')))",'0.0%')
addmeasure('Customers','消费贡献',"DIVIDE([历史消费额],CALCULATE([历史消费额],REMOVEFILTERS('Segment')))",'0.0%')
addmeasure('Customers','平均未购买天数','DIVIDE(SUM(Customers[RecencyTotal]),[客户数])','0.0')
addmeasure('OrdersDaily','订单量','SUM(OrdersDaily[Orders])','#,0')
addmeasure('OrdersDaily','消费额','DIVIDE(SUM(OrdersDaily[SalesCents]),100)')
addmeasure('OrdersDaily','平均订单金额','DIVIDE([消费额],[订单量])')
addmeasure('OrdersDaily','交易门店数','DISTINCTCOUNT(OrdersDaily[Store])','#,0')
for tab in ['Experiment','ExperimentOverall']:
 suffix='' if tab=='Experiment' else '（总体）'
 for name,expr,fmt in [('短信组人数',f'SUM({tab}[sms_n])','#,0'),('对照组人数',f'SUM({tab}[control_n])','#,0'),('短信购买率',f'DIVIDE(SUM({tab}[sms_buyers]),SUM({tab}[sms_n]))','0.00%'),('对照购买率',f'DIVIDE(SUM({tab}[control_buyers]),SUM({tab}[control_n]))','0.00%')]:addmeasure(tab,name+suffix,expr,fmt)
 addmeasure(tab,'购买率差'+suffix,f'100*([短信购买率{suffix}]-[对照购买率{suffix}])','+0.00;-0.00;0.00')
 for name,sign in [('区间下界','-'),('区间上界','+')]:
  addmeasure(tab,name+suffix,f'VAR p1=[短信购买率{suffix}] VAR p0=[对照购买率{suffix}] VAR n1=[短信组人数{suffix}] VAR n0=[对照组人数{suffix}] RETURN IF(n1>0 && n0>0, [购买率差{suffix}] {sign} 1.95996398454005*100*SQRT(DIVIDE(p1*(1-p1),n1)+DIVIDE(p0*(1-p0),n0)))','+0.00;-0.00;0.00')
for name,col in [('历史客户规模','HistoryClients'),('商品明细规模','Lines'),('待评客户数','OfficialScores')]:addmeasure('Overview',name,f'MAX(Overview[{col}])','#,0')
for tab,cols in {'Policies':{'策略购买率差':'uplift_pp','策略下界':'ci_low_pp','策略上界':'ci_high_pp'},'Comparisons':{'领先幅度':'difference_pp','领先下界':'ci_low_pp','领先上界':'ci_high_pp'},'Optimization':{'平均购买率差':'mean_uplift_pp','领先随机':'mean_vs_random_pp','领先原模型':'mean_vs_base_t_pp','胜出折数':'folds_positive_vs_base_t'},'Curves':{'覆盖购买率差':'uplift_pp'},'Cohort':{'完整月复购率':'repeat_rate','客群规模':'cohort_customers'}}.items():
 for name,col in cols.items():addmeasure(tab,name,f'SELECTEDVALUE({tab}[{col}])','0.0%' if name=='完整月复购率' else '+0.00;-0.00;0.00' if '差' in name or '领先' in name else '#,0')
relationships=[]
for fact,column,dim,target in [('Customers','Segment','Segment','Segment'),('OrdersDaily','Segment','Segment','Segment'),('Experiment','Segment','Segment','Segment'),('OrdersDaily','Date','Dates','Date'),('OrdersDaily','Store','Stores','Store'),('Policies','Sample','Sample','Sample'),('Comparisons','Sample','Sample','Sample')]:
 relationships.append({'name':hashlib.sha1((fact+column+dim).encode()).hexdigest()[:24],'fromTable':fact,'fromColumn':column,'toTable':dim,'toColumn':target,'crossFilteringBehavior':'oneDirection','fromCardinality':'many','toCardinality':'one'})
dump(MODEL/'model.bim',{'name':'X5RetailHero','compatibilityLevel':1601,'model':{'culture':'zh-CN','defaultPowerBIDataSourceVersion':'powerBI_V3','sourceQueryCulture':'zh-CN','tables':tables,'relationships':relationships}})
dump(MODEL/'definition.pbism',{'$schema':schema('fabric/item/semanticModel/definitionProperties/1.0.0'),'version':'4.2','settings':{'qnaEnabled':False}})
dump(OUT/'X5RetailHero.pbip',{'$schema':schema('fabric/pbip/pbipProperties/1.0.0'),'version':'1.0','artifacts':[{'report':{'path':'X5RetailHero.Report'}}],'settings':{'enableAutoRecovery':True}})
dump(REPORT/'definition.pbir',{'$schema':schema('fabric/item/report/definitionProperties/2.0.0'),'version':'4.0','datasetReference':{'byPath':{'path':'../X5RetailHero.SemanticModel'}}})
report={'$schema':schema('fabric/item/report/definition/report/3.0.0'),'themeCollection':{'customTheme':{'name':'X5Theme','reportVersionAtImport':{'visual':'2.0.0','report':'3.0.0','page':'2.0.0'},'type':'RegisteredResources'}},'resourcePackages':[{'name':'RegisteredResources','type':'RegisteredResources','items':[{'name':'X5Theme','path':'X5Theme.json','type':'CustomTheme'}]}],'settings':{'useEnhancedTooltips':True,'defaultFilterActionIsDataFilter':True}}
dump(REPORT/'definition/report.json',report)
dump(REPORT/'definition/version.json',{'$schema':schema('fabric/item/report/definition/versionMetadata/1.0.0'),'version':'2.0.0'})
dump(REPORT/'StaticResources/RegisteredResources/X5Theme.json',{'name':'X5Theme','dataColors':['#66439A','#D6AD2F','#9272B6','#A7ACB7','#41324F'],'background':'#F7F5FA','foreground':'#30243F','tableAccent':'#66439A','textClasses':{'title':{'fontFace':'SimHei','fontSize':15},'header':{'fontFace':'SimHei','fontSize':13},'label':{'fontFace':'SimSun','fontSize':11},'callout':{'fontFace':'Times New Roman','fontSize':30}}})
(OUT/'measures.dax').write_text('\n\n'.join(f'-- {t} | {fmt}\n[{n}] = {e}' for t,n,e,fmt in allmeasures))
class Page:
 def __init__(self,i,title,subtitle):
  self.id=f'P{i:02}';self.folder=REPORT/'definition/pages'/self.id;self.z=0
  dump(self.folder/'page.json',{'$schema':schema('fabric/item/report/definition/page/2.0.0'),'name':self.id,'displayName':f'{i:02} {title}','displayOption':'FitToPage','height':900,'width':1440})
  self.text(30,18,1380,48,title,26);self.text(30,65,1380,42,subtitle,12)
 def put(self,x,y,w,h,v):
  self.z+=1;uid=hashlib.sha1((self.id+str(self.z)).encode()).hexdigest()[:20]
  dump(self.folder/'visuals'/uid/'visual.json',{'$schema':schema('fabric/item/report/definition/visualContainer/2.0.0'),'name':uid,'position':{'x':x,'y':y,'width':w,'height':h,'z':self.z,'tabOrder':self.z},'visual':v})
 def text(self,x,y,w,h,text,size=12):self.put(x,y,w,h,{'visualType':'textbox','objects':{'general':[{'properties':{'paragraphs':[{'textRuns':[{'value':text,'textStyle':{'fontFamily':'SimHei' if size>15 else 'SimSun','fontSize':f'{size}pt','color':'#41304F'}}]}]}}]}})
 def visual(self,kind,title,x,y,w,h,roles):
  states={}
  for role,fields in roles.items():
   projections=[]
   for table,field,is_measure in fields:
    assert table in types and (field in types[table] or any(t==table and n==field for t,n,_,_ in allmeasures)),(table,field)
    projections.append({'field':{'Measure' if is_measure else 'Column':{'Expression':{'SourceRef':{'Entity':table}},'Property':field}},'queryRef':table+'.'+field,'nativeQueryRef':field,'active':True})
   states[role]={'projections':projections}
  self.put(x,y,w,h,{'visualType':kind,'drillFilterOtherVisuals':True,'visualContainerObjects':{'title':[{'properties':{'show':literal('true'),'text':txt(title),'fontSize':literal('14D'),'fontFamily':txt('SimHei')}}],'background':[{'properties':{'show':literal('true'),'color':{'solid':{'color':txt('#FFFFFF')}},'transparency':literal('0D')}}]},'query':{'queryState':states}})
 def card(self,title,t,m,x,y=120,w=330):self.visual('card',title,x,y,w,105,{'Values':[(t,m,True)]})
 def table(self,title,fields,x,y,w,h):self.visual('tableEx',title,x,y,w,h,{'Values':fields})
 def slicer(self,title,t,f,x,y,w=260):self.visual('slicer',title,x,y,w,90,{'Values':[(t,f,False)]})
def c(t,f):return t,f,False
def m(t,f):return t,f,True
p=Page(1,'零售客户经营与营销效果','公开历史数据研究｜客户行为基于120,022名训练客户；实验与策略页面标明各自样本范围。')
for x,t,f,title in [(30,'Overview','历史客户规模','全量历史客户'),(380,'Customers','客户数','训练样本客户'),(730,'ExperimentOverall','购买率差（总体）','训练样本购买率差 / pp'),(1080,'Overview','待评客户数','已输出预测的官方客户')]:p.card(title,t,f,x)
p.visual('clusteredColumnChart','客群客户占比与消费贡献（训练样本）',30,245,810,340,{'Category':[c('Segment','Segment')],'Y':[m('Customers','客户占比'),m('Customers','消费贡献')]})
p.table('候选相对基线的差异 · 分阶段 / pp',[c('Comparisons','Sample'),c('Comparisons','comparator'),m('Comparisons','领先幅度'),m('Comparisons','领先下界'),m('Comparisons','领先上界')],860,245,550,340)
p.text(40,620,1340,90,'客户维护：15.1%的高价值客户贡献37.3%的历史消费额。\n投放判断：模型相对随机仅领先0.29个百分点，95%区间跨零；建议先做同预算随机试点。',19)
p.text(40,758,1340,85,'范围说明：右侧表同时列出验证集与独立保留集，Sample用于识别阶段。金额沿用源数据单位；未提供成本与毛利，不能推算真实利润。')
p=Page(2,'客户价值与复购','训练样本｜客群与购买近期程度筛选作用于客户指标；Cohort表独立展示完整月份，避免误读窗口边界。')
p.slicer('客户分群','Segment','Segment',30,115,660);p.slicer('购买近期程度','Customers','RecencyBand',720,115,690)
for x,f,title in [(30,'客户数','筛选客户数'),(380,'历史消费额','历史消费额 / 源单位'),(730,'客单价','每单平均消费'),(1080,'平均未购买天数','平均未购买天数')]:p.card(title,'Customers',f,x,220)
p.visual('clusteredColumnChart','客群规模与消费贡献',30,350,740,330,{'Category':[c('Segment','Segment')],'Y':[m('Customers','客户占比'),m('Customers','消费贡献')]})
p.table('完整月Cohort复购（空白表示不完整或不可观察）',[c('Cohort','cohort_month'),c('Cohort','activity_month'),c('Cohort','status'),m('Cohort','完整月复购率')],790,350,620,330)
p.table('客户经营指标',[c('Segment','Segment'),m('Customers','客户数'),m('Customers','历史订单数'),m('Customers','历史消费额'),m('Customers','客单价')],30,700,1380,160)
p=Page(3,'消费趋势与门店表现','仅训练客户的历史订单｜日期、门店、客群筛选共同作用于本页所有订单指标；首末月份记录不完整。')
p.slicer('交易日期','Dates','Date',30,110,440);p.slicer('匿名门店编号','Stores','Store',490,110,440);p.slicer('客户分群','Segment','Segment',950,110,460)
for x,f,title in [(30,'订单量','筛选订单量'),(380,'消费额','消费额 / 源单位'),(730,'平均订单金额','平均订单金额'),(1080,'交易门店数','有交易门店数')]:p.card(title,'OrdersDaily',f,x,220)
p.visual('lineChart','每日消费额',30,350,850,330,{'Category':[c('Dates','Date')],'Y':[m('OrdersDaily','消费额')]})
p.table('门店表现 · 点击列标题可排序',[c('Stores','Store'),m('OrdersDaily','订单量'),m('OrdersDaily','消费额'),m('OrdersDaily','平均订单金额')],900,350,510,330)
p.visual('clusteredColumnChart','每日订单量',30,700,1380,170,{'Category':[c('Dates','Date')],'Y':[m('OrdersDaily','订单量')]})
p=Page(4,'短信营销效果','训练样本｜按客群查看短信组与对照组；购买率和区间由当前选中客群的分子、分母重新计算。')
p.slicer('分析客群','Segment','Segment',30,110,1380)
for x,f,title in [(30,'短信组人数','短信组客户'),(380,'对照组人数','对照组客户'),(730,'购买率差','购买率差 / pp'),(1080,'短信购买率','短信组购买率')]:p.card(title,'Experiment',f,x,220)
p.visual('clusteredColumnChart','各客群两组购买率',30,350,810,330,{'Category':[c('Segment','Segment')],'Y':[m('Experiment','短信购买率'),m('Experiment','对照购买率')]})
p.table('购买率差及95%区间 / pp',[c('Segment','Segment'),m('Experiment','购买率差'),m('Experiment','区间下界'),m('Experiment','区间上界')],860,350,550,330)
p.text(40,715,1320,120,'业务解读：高历史消费不等于更高短信增量。高价值活跃客群的区间跨零，不应仅按历史价值扩大短信触达。\n当前为历史组间比较，因果解释依赖可靠的实验分配和一致的统计窗口；已检查特征相近不能单独证明随机分配。',17)
p=Page(5,'选客策略与模型优化','固定30%覆盖比例比较｜评估阶段筛选只作用于策略对照表；覆盖曲线固定为验证集，优化固定为开发集。')
p.slicer('评估阶段','Sample','Sample',30,110,1380)
p.table('策略效果及95%区间 / pp',[c('Sample','Sample'),c('Policies','label'),m('Policies','策略购买率差'),m('Policies','策略下界'),m('Policies','策略上界')],30,220,790,260)
p.table('候选相对基线 / pp',[c('Comparisons','Sample'),c('Comparisons','comparator'),m('Comparisons','领先幅度'),m('Comparisons','领先下界'),m('Comparisons','领先上界')],840,220,570,260)
p.visual('lineChart','验证集 · 不同覆盖比例下的购买率差',30,500,790,270,{'Category':[c('Curves','reach_pct')],'Y':[m('Curves','覆盖购买率差')],'Series':[c('Curves','policy')]})
p.table('开发集3次×5折 · 优化结果 / pp',[c('Optimization','model'),m('Optimization','平均购买率差'),m('Optimization','领先原模型'),m('Optimization','胜出折数')],840,500,570,270)
p.text(40,790,1330,80,'优化判断：增强方案平均仅改善0.02个百分点，9/15折优于原方案，暂不替换。独立保留集仅评价30%覆盖，不外推其他预算比例。',16)
dump(REPORT/'definition/pages/pages.json',{'$schema':schema('fabric/item/report/definition/pagesMetadata/1.0.0'),'pageOrder':[f'P{i:02}' for i in range(1,6)],'activePageName':'P01'})
print('Generated 5 native pages,',len(tables),'tables,',len(allmeasures),'measures')
