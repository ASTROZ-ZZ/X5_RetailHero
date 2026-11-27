from pathlib import Path
import pandas as pd,json
O=Path(__file__).resolve().parents[1]
REPORT=O.parent/'results/reporting'
OUTPUT=REPORT/'X5_RetailHero_经营分析数据看板.html'
def read(n):return pd.read_csv(O/'data'/f'{n}.csv',dtype={'Store':str})
x=read('OrdersDaily'); total_orders=int(x.Orders.sum()); total_cents=int(x.SalesCents.sum())
top=x.groupby('Store').SalesCents.sum().nlargest(20).index.tolist()
x['Store']=x.Store.where(x.Store.isin(top),'其他门店')
x=x.groupby(['Date','Store','Segment'],as_index=False)[['Orders','SalesCents']].sum()
assert (int(x.Orders.sum()),int(x.SalesCents.sum()))==(total_orders,total_cents)
assert (total_orders,total_cents)==(2411872,103384700372)
def clean(df):return json.loads(df.to_json(orient='records',force_ascii=False))
d={n:clean(read(n)) for n in ['Overview','Customers','Segments','Cohort','Experiment','ExperimentOverall','Policies','Comparisons','Curves','Optimization','Repeats']}
d['daily']={'columns':list(x),'rows':json.loads(x.to_json(orient='values',force_ascii=False))};d['topStores']=top
html=(O/'tools/dashboard_template.html').read_text()
REPORT.mkdir(parents=True,exist_ok=True)
OUTPUT.write_text(html.replace('__DATA__',json.dumps(d,ensure_ascii=False,separators=(',',':'))))
print('Browser daily rows:',len(x),'HTML bytes:',OUTPUT.stat().st_size)
