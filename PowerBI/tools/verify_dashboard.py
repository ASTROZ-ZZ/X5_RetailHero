"""Verify the portable Power BI project against its local schema and source totals.

Run with an environment containing jsonschema, for example /opt/anaconda3/bin/python.
"""
from pathlib import Path
import base64,csv,gzip,json,re,warnings
from jsonschema import Draft202012Validator,RefResolver

warnings.filterwarnings('ignore',category=DeprecationWarning)
out=Path(__file__).resolve().parents[1]
schemas=json.loads((out/'validation/official_schemas.json').read_text())
prefix='https://developer.microsoft.com/json-schemas/'
store={u:v for k,v in schemas.items() for u in (prefix+k,v['$id'])}
documents=[out/'X5RetailHero.pbip',out/'X5RetailHero.Report/definition.pbir',out/'X5RetailHero.SemanticModel/definition.pbism',*(out/'X5RetailHero.Report').rglob('*.json')]
checked=0
for file in documents:
    obj=json.loads(file.read_text())
    if not (url:=obj.get('$schema')):continue
    assert url in store,(file,url)
    validator=Draft202012Validator(store[url],resolver=RefResolver.from_schema(store[url],store=store))
    errors=list(validator.iter_errors(obj))
    assert not errors,(file,errors[0])
    checked+=1

model=json.loads((out/'X5RetailHero.SemanticModel/model.bim').read_text())['model']
tables={t['name']:t for t in model['tables']}
assert len(tables)==16
for t in tables.values():
    cols=[c['name'] for c in t['columns']]
    expr=t['partitions'][0]['source']['expression']
    assert 'Source = Table.FromRows(Rows, {' in expr[3],t['name']
    encoded=json.loads('['+expr[1].split('{',1)[1].split('}',1)[0]+']')
    rows=json.loads(gzip.decompress(base64.b64decode(''.join(encoded))))
    with (out/'data'/f"{t['name']}.csv").open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        assert reader.fieldnames==cols,t['name']
        count=0;sum_orders=0;sum_cents=0;first=None;last=None
        for raw in reader:
            expected=[None if raw[c]=='' else raw[c] if t['columns'][i]['dataType']=='string' else int(float(raw[c])) if t['columns'][i]['dataType']=='int64' else float(raw[c]) for i,c in enumerate(cols)]
            if count==0:first=expected
            last=expected
            if t['name']=='OrdersDaily':
                sum_orders+=int(raw['Orders']);sum_cents+=int(raw['SalesCents'])
            count+=1
        assert len(rows)==count,(t['name'],len(rows),count)
        assert rows[0]==first and rows[-1]==last,t['name']
        if t['name']=='OrdersDaily':assert (sum_orders,sum_cents)==(2411872,103384700372)
for rel in model['relationships']:
    assert rel['fromTable'] in tables and rel['toTable'] in tables
    for key,table,col in [('from',rel['fromTable'],rel['fromColumn']),('to',rel['toTable'],rel['toColumn'])]:
        assert col in [c['name'] for c in tables[table]['columns']],(table,col)

visuals=list((out/'X5RetailHero.Report/definition/pages').rglob('visual.json'))
assert len(list((out/'X5RetailHero.Report/definition/pages').glob('P*/page.json')))==5
for p in visuals:
    v=json.loads(p.read_text())['visual']
    for role,data in v.get('query',{}).get('queryState',{}).items():
        for proj in data['projections']:
            field=proj['field'];kind='Measure' if 'Measure' in field else 'Column'
            obj=field[kind];tab=obj['Expression']['SourceRef']['Entity'];name=obj['Property']
            assert tab in tables,(p,tab)
            assert name in [x['name'] for x in tables[tab]['measures' if kind=='Measure' else 'columns']],(p,tab,name)

with (out/'data/Overview.csv').open(encoding='utf-8-sig') as f:overview=next(csv.DictReader(f))
assert int(overview['HistoryClients'])==400162 and int(overview['TrainClients'])==120022
assert int(overview['TrainOrders'])==2411872 and int(overview['Lines'])==45786568
with (out/'data/Customers.csv').open(encoding='utf-8-sig') as f:customers=list(csv.DictReader(f))
assert (sum(int(r['Clients']) for r in customers),sum(int(r['Orders']) for r in customers),sum(int(r['SalesCents']) for r in customers))==(120022,2411872,103384700372)
with (out/'data/Comparisons.csv').open(encoding='utf-8-sig') as f:comparisons=list(csv.DictReader(f))
holdout=next(r for r in comparisons if r['Sample']=='独立保留集' and r['comparator']=='random')
assert abs(float(holdout['difference_pp'])-.2949396483)<1e-6
assert float(holdout['ci_low_pp'])<0<float(holdout['ci_high_pp'])

result={'status':'PASS','official_schema_documents':checked,'semantic_tables':len(tables),'native_pages':5,'native_visuals':len(visuals),'train_orders':2411872,'sales_cents':103384700372,'holdout_vs_random_pp':float(holdout['difference_pp']),'holdout_vs_random_ci_pp':[float(holdout['ci_low_pp']),float(holdout['ci_high_pp'])]}
(out/'validation/verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False))
