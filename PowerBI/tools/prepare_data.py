from pathlib import Path
import pandas as pd
import json,sqlite3,tempfile,hashlib
ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'PowerBI'; R=ROOT/'results'
def read(p):return pd.read_csv(R/p,encoding='utf-8-sig')
def save(name,df):df.to_csv(OUT/'data'/f'{name}.csv',index=False,encoding='utf-8-sig');return df
customers=read('02_customer_analysis/tables/customer_features.csv')
customers.client_id=customers.client_id.astype(str)
with tempfile.TemporaryDirectory(prefix='x5-dashboard-') as tmp:
 db=sqlite3.connect(Path(tmp)/'work.sqlite'); db.execute('PRAGMA journal_mode=OFF')
 customers[['client_id','segment']].to_sql('customers',db,index=False)
 db.execute('CREATE UNIQUE INDEX client_key ON customers(client_id)')
 for chunk in pd.read_csv(R/'02_customer_analysis/tables/training_orders.csv.gz',dtype={'client_id':str,'transaction_id':str,'store_id':str},chunksize=250000):
  chunk['cents']=(chunk.purchase_sum*100).round().astype('int64')
  chunk[['client_id','transaction_datetime','store_id','cents']].to_sql('orders',db,index=False,if_exists='append')
 df=pd.read_sql_query((OUT/'tools/aggregate.sql').read_text(),db)
 n,total=db.execute('SELECT count(*),sum(cents) FROM orders').fetchone(); db.close()
 assert int(df.Orders.sum())==n==2411872
 assert int(df.SalesCents.sum())==total==103384700372
 save('OrdersDaily',df)
 print('OrdersDaily',len(df),flush=True)
customers['Cents']=(customers.monetary*100).round().astype('int64')
customers['RecencyBand']=pd.cut(customers.recency_days,[-1,2,9,29,10000],labels=['01 近2天','02 3–9天','03 10–29天','04 30天及以上']).astype(str)
buckets=customers.groupby(['segment','cohort_month','RecencyBand'],observed=True).agg(Clients=('client_id','size'),Orders=('frequency','sum'),SalesCents=('Cents','sum'),RecencyTotal=('recency_days','sum')).reset_index().rename(columns={'segment':'Segment','cohort_month':'CohortMonth'})
save('Customers',buckets)
seg=read('02_customer_analysis/tables/segment_summary.csv');save('Segments',seg.rename(columns={'segment':'Segment'}))
save('Segment',pd.DataFrame({'Segment':seg.segment}))
save('Dates',pd.DataFrame({'Date':sorted(df.Date.unique())}))
save('Stores',pd.DataFrame({'Store':sorted(df.Store.unique())}))
cohort=read('02_customer_analysis/tables/cohort_repeat.csv');save('Cohort',cohort)
exp=read('03_sms_experiment/tables/purchase_rate_effects.csv')
save('Experiment',exp[exp.segment.ne('整体')].rename(columns={'segment':'Segment'}))
save('ExperimentOverall',exp[exp.segment.eq('整体')].rename(columns={'segment':'Segment'}))
policies=[]
for sample,path in [('验证集','04_uplift_baselines/tables/validation_at30.csv'),('独立保留集','05_holdout_evaluation/tables/holdout_at30.csv')]:
 f=read(path);f['Sample']=sample;policies.append(f)
save('Policies',pd.concat(policies,ignore_index=True))
comparisons=[]
for sample,path in [('验证集','04_uplift_baselines/tables/candidate_vs_baselines.csv'),('独立保留集','05_holdout_evaluation/tables/holdout_candidate_vs_baselines.csv')]:
 f=read(path);f['Sample']=sample;comparisons.append(f)
save('Comparisons',pd.concat(comparisons,ignore_index=True))
curves=read('04_uplift_baselines/tables/validation_curves.csv');save('Curves',curves)
save('Optimization',read('07_uplift_optimization/tables/model_summary.csv'))
save('Repeats',read('07_uplift_optimization/tables/repeat_summary.csv'))
summary=json.loads((R/'02_customer_analysis/metadata/analysis_summary.json').read_text())
source=read('01_data_audit/tables/table_summary.csv').set_index('table')
save('Overview',pd.DataFrame([{'HistoryClients':int(source.loc['clients','rows']),'Lines':int(source.loc['purchases','rows']),'TrainClients':len(customers),'TrainOrders':n,'SalesCents':total,'OfficialScores':200123}]))
save('Sample',pd.DataFrame({'Sample':['验证集','独立保留集']}))
manifest={'status':'PASS','training_customers':len(customers),'orders':n,'sales_cents':total,'aggregate_rows':len(df),'scope':'fixed training customers only; model metrics retain their own evaluation population','source_files':{},'files':{}}
for p in sorted((OUT/'data').glob('*.csv')):
 manifest['files'][p.name]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
for rel in ['02_customer_analysis/tables/customer_features.csv','02_customer_analysis/tables/training_orders.csv.gz','03_sms_experiment/tables/purchase_rate_effects.csv','04_uplift_baselines/tables/validation_at30.csv','05_holdout_evaluation/tables/holdout_at30.csv','07_uplift_optimization/tables/model_summary.csv']:
 p=R/rel;manifest['source_files'][rel]=hashlib.sha256(p.read_bytes()).hexdigest()
(OUT/'data_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in manifest.items() if k not in ('files','source_files')},ensure_ascii=False),flush=True)
