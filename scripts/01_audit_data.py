#!/usr/bin/env python3
"""Full-file X5 audit. Raw CSVs are read-only; pandas/numpy are the only dependencies."""
from pathlib import Path
from stage01_layout import output_path
from collections import Counter
import argparse
import hashlib
import json
import math
import platform
import sqlite3
import sys
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MEANINGS = {
    'client_id': '客户标识；字符串，保留前导零',
    'product_id': '商品标识；字符串',
    'transaction_id': '交易标识；跨客户可能复用，交易键使用 client_id + transaction_id',
    'transaction_datetime': '历史交易时间；原始数据未注明时区，不擅自转换',
    'first_issue_date': '首次发卡时间；缺少快照生成时间，使用前核对触达前可用性',
    'first_redeem_date': '首次积分兑换时间；可能晚于历史消费窗口，须按预测截止时间截断',
    'age': '记录年龄；极端值需标记，缺少快照生成时间',
    'gender': '性别编码；U 作为未知类别保留',
    'treatment_flg': '是否短信触达；1 为处理组，0 为对照组',
    'target': '触达后是否购买；仅作标签，禁止进入行为特征',
    'uplift': '提交样例分数；非真实标签，不作为特征或训练目标',
    'purchase_sum': '交易金额字段；在商品行重复时不得逐行累计为销售额',
    'product_quantity': '商品行数量；非正数作为待核实业务异常，不自动删除',
    'store_id': '门店标识；字符串',
    'netto': '商品净含量字段；具体计量单位需进一步核对',
    'is_own_trademark': '是否自有品牌', 'is_alcohol': '是否酒类',
    'trn_sum_from_iss': '商品行金额相关字段；业务定义需进一步核对',
    'trn_sum_from_red': '商品行金额相关字段；业务定义及缺失含义需进一步核对',
}


def export(rows, path):
    pd.DataFrame(rows).to_csv(path, index=False, encoding='utf-8-sig')


def split_clients(train, seed):
    """Stable SHA256 order within treatment x outcome strata, 60/20/20."""
    parts = []
    for _, group in train.groupby(['treatment_flg', 'target'], sort=True):
        group = group.copy()
        group['_hash'] = group.client_id.map(
            lambda x: hashlib.sha256(f'{seed}:{x}'.encode()).hexdigest())
        group = group.sort_values(['_hash', 'client_id'])
        n = len(group)
        a, b = int(n * .6), int(n * .8)
        group['split'] = ['train'] * a + ['validation'] * (b-a) + ['holdout'] * (n-b)
        parts.append(group[['client_id', 'split']])
    return pd.concat(parts).sort_values('client_id').reset_index(drop=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--chunk-size', type=int, default=500_000)
    parser.add_argument('--seed', type=int, default=20261116)
    parser.add_argument('--output', type=Path, default=ROOT / 'results' / '01_data_audit')
    args = parser.parse_args()
    if args.chunk_size <= 0:
        parser.error('--chunk-size must be positive')
    start = time.time()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    data = ROOT / 'data'
    checks, profiles, numeric, dictionary, files = [], [], [], [], []
    def check(name, count, note='', severity='warning'):
        checks.append(dict(check=name, issue_count=int(count),
                           status='PASS' if count == 0 else severity.upper(), note=note))
    def profile(name, frame):
        for col in frame:
            s = frame[col]
            missing = s.isna() | s.eq('')
            profiles.append(dict(table=name, field=col, rows=len(s), missing=int(missing.sum()),
                                 missing_rate=float(missing.mean()), unique_nonmissing=int(s[~missing].nunique())))
    tables = {}
    for name in ['clients', 'products', 'uplift_train', 'uplift_test', 'uplift_sample_submission']:
        frame = pd.read_csv(data / f'{name}.csv', dtype=str)
        tables[name] = frame
        profile(name, frame)
        key = 'product_id' if name == 'products' else 'client_id'
        check(name + '.duplicate_key', frame[key].duplicated().sum(), severity='error')
        check(name + '.missing_key', frame[key].isna().sum(), severity='error')
        check(name + '.duplicate_rows', frame.duplicated().sum())
        for col in frame:
            if col.endswith('_id') or col == 'client_id' or col.startswith('level_'):
                continue
            if col.endswith('_date'):
                converted = pd.to_datetime(frame[col], errors='coerce')
                check(name + '.' + col + '.invalid_date', (frame[col].notna() & converted.isna()).sum())
                numeric.append(dict(table=name, field=col, min=str(converted.min()), max=str(converted.max())))
            elif col != 'gender':
                converted = pd.to_numeric(frame[col], errors='coerce')
                check(name + '.' + col + '.invalid_number', (frame[col].notna() & converted.isna()).sum())
                if converted.notna().any():
                    numeric.append(dict(table=name, field=col, min=float(converted.min()), max=float(converted.max()),
                                        negative=int((converted < 0).sum()), zero=int((converted == 0).sum())))
        print(f'{name}: {len(frame):,} rows', flush=True)

    train, clients, products = tables['uplift_train'], tables['clients'], tables['products']
    client_ids, product_ids = set(clients.client_id), set(products.product_id)
    train_ids, test_ids = set(train.client_id), set(tables['uplift_test'].client_id)
    check('train_test.client_overlap', len(train_ids & test_ids), severity='error')
    for name in ['uplift_train', 'uplift_test']:
        check(name + '.clients_not_found', len(set(tables[name].client_id) - client_ids), severity='error')
    check('submission.client_set_difference', len(set(tables['uplift_sample_submission'].client_id) ^ test_ids), severity='error')
    for col in ['treatment_flg', 'target']:
        check('uplift_train.' + col + '.invalid_binary', (~train[col].isin(['0', '1'])).sum(), severity='error')
    ages = pd.to_numeric(clients.age, errors='coerce')
    check('clients.age.outside_0_100', ((ages < 0) | (ages > 100)).sum(), '0—100 为分析用筛查阈值，不代表官方清洗规则')
    export([dict(gender=k, rows=v) for k,v in clients.gender.fillna('<missing>').value_counts().items()], output_path(out, 'gender_counts.csv'))

    # Disk-backed transaction aggregation makes checks exact across CSV chunk boundaries.
    db_path = output_path(out, '_audit_work.sqlite')
    if db_path.exists():
        db_path.unlink()
    db = sqlite3.connect(db_path)
    db.execute('PRAGMA journal_mode=OFF')
    db.execute('PRAGMA synchronous=OFF')
    db.execute('CREATE TABLE tx (id TEXT PRIMARY KEY, cmin TEXT, cmax TEXT, dmin TEXT, dmax TEXT, smin TEXT, smax TEXT, pmin REAL, pmax REAL, n INTEGER)')
    sql = '''INSERT INTO tx VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
        cmin=min(cmin,excluded.cmin),cmax=max(cmax,excluded.cmax),
        dmin=min(dmin,excluded.dmin),dmax=max(dmax,excluded.dmax),
        smin=min(smin,excluded.smin),smax=max(smax,excluded.smax),
        pmin=min(pmin,excluded.pmin),pmax=max(pmax,excluded.pmax),n=n+excluded.n'''
    row_count = 0
    missing = Counter()
    bad_numeric = Counter()
    neg = Counter()
    zeros = Counter()
    minima, maxima = {}, {}
    observed_users, observed_products = set(), set()
    missing_clients = missing_products = invalid_dates = missing_tx = 0
    within_duplicate_rows = 0
    date_min = date_max = None
    months = Counter()
    purchase_columns = None
    for i, chunk in enumerate(pd.read_csv(data/'purchases.csv', dtype=str, chunksize=args.chunk_size)):
        purchase_columns = list(chunk.columns)
        row_count += len(chunk)
        missing.update(chunk.isna().sum().to_dict())
        observed_users.update(chunk.client_id.dropna().unique())
        observed_products.update(chunk.product_id.dropna().unique())
        missing_clients += int((~chunk.client_id.isin(client_ids)).sum())
        missing_products += int((~chunk.product_id.isin(product_ids)).sum())
        within_duplicate_rows += int(chunk.duplicated().sum())
        dt = pd.to_datetime(chunk.transaction_datetime, errors='coerce')
        invalid_dates += int((chunk.transaction_datetime.notna() & dt.isna()).sum())
        if dt.notna().any():
            date_min = dt.min() if date_min is None else min(date_min, dt.min())
            date_max = dt.max() if date_max is None else max(date_max, dt.max())
        # Validated ISO source prefix avoids platform-dependent strftime overhead.
        months.update(chunk.loc[dt.notna(), 'transaction_datetime'].str.slice(0, 7).value_counts().to_dict())
        for col in purchase_columns:
            if col.endswith('_id') or col == 'transaction_datetime':
                continue
            values = pd.to_numeric(chunk[col], errors='coerce')
            bad_numeric[col] += int((chunk[col].notna() & values.isna()).sum())
            neg[col] += int((values < 0).sum())
            zeros[col] += int((values == 0).sum())
            if values.notna().any():
                minima[col] = min(minima.get(col, math.inf), float(values.min()))
                maxima[col] = max(maxima.get(col, -math.inf), float(values.max()))
            if col == 'purchase_sum':
                chunk[col] = values
        missing_tx += int(chunk.transaction_id.isna().sum())
        # Hash grouping on all metadata keys avoids slow Python object min/max per group.
        g = chunk.groupby(['transaction_id','client_id','transaction_datetime','store_id','purchase_sum'],
                          sort=False, dropna=False).size().reset_index(name='n')
        def transaction_records():
            for tid, cid, date, store, amount, n in g.itertuples(index=False, name=None):
                if pd.isna(tid):
                    continue
                cid = '' if pd.isna(cid) else cid
                date = '' if pd.isna(date) else date
                store = '' if pd.isna(store) else store
                amount = None if pd.isna(amount) else amount
                # Customer-scoped transaction key; source transaction IDs may repeat across customers.
                yield (cid+':'+tid,cid,cid,date,date,store,store,amount,amount,n)
        records = transaction_records()
        db.executemany(sql, records)
        db.commit()
        print(f'purchases: {row_count:,} rows scanned ({time.time()-start:.0f}s)', flush=True)
    for col in purchase_columns:
        profiles.append(dict(table='purchases', field=col, rows=row_count, missing=missing[col],
                             missing_rate=missing[col]/row_count, unique_nonmissing='not_computed'))
    for col in minima:
        numeric.append(dict(table='purchases', field=col, min=minima[col], max=maxima[col], negative=neg[col], zero=zeros[col]))
        check('purchases.'+col+'.invalid_number', bad_numeric[col])
    check('purchases.clients_not_found_rows', missing_clients, severity='error')
    check('purchases.products_not_found_rows', missing_products, severity='error')
    check('purchases.invalid_transaction_datetime', invalid_dates, severity='error')
    check('purchases.missing_transaction_id', missing_tx, severity='error')
    check('purchases.exact_duplicate_rows_within_chunks', within_duplicate_rows,
          '只检查每批内完全重复行；跨批重复行未检查，不能据此声称全量无重复')
    check('purchases.nonpositive_product_quantity', neg['product_quantity']+zeros['product_quantity'])
    tx_count, repeated, client_conflict, date_conflict, store_conflict, amount_conflict = db.execute('''SELECT count(*),sum(n>1),
        sum(cmin<>cmax),sum(dmin<>dmax),sum(smin<>smax),sum(pmin<>pmax) FROM tx''').fetchone()
    collision_count = db.execute('''
        SELECT count(*) FROM (SELECT substr(id,instr(id,':')+1) AS source_id FROM tx
        GROUP BY source_id HAVING count(*)>1)''').fetchone()[0]
    check('transaction.id_reused_across_customers', collision_count, '全局交易编号存在跨客户复用；采用客户+交易编号组合键，不删除原始记录')
    cached_rows = db.execute('SELECT sum(n) FROM tx').fetchone()[0]
    check('transaction.cached_row_reconciliation', abs(cached_rows-row_count), severity='error')
    for name,count in [('client',client_conflict),('datetime',date_conflict),('store',store_conflict),('purchase_sum',amount_conflict)]:
        check('transaction.inconsistent_'+name, count, '全量跨批检查；缺失值另见字段缺失表', severity='error')
    export([dict(client_id=r[0], transactions=r[1], first_purchase=r[2], last_purchase=r[3]) for r in db.execute(
        'SELECT cmin,count(*),min(dmin),max(dmax) FROM tx GROUP BY cmin')], output_path(out, 'client_history_coverage.csv'))
    export([dict(field='transaction_datetime', min=str(date_min), max=str(date_max), timezone='unspecified_in_source')], output_path(out, 'purchase_time_range.csv'))
    export([dict(month=k, purchase_rows=v) for k,v in sorted(months.items())], output_path(out, 'monthly_purchase_rows.csv'))
    for name, ids in [('clients',client_ids),('uplift_train',train_ids),('uplift_test',test_ids)]:
        check(name+'.without_purchase_history', len(ids-observed_users), '保留客户，后续用零行为及缺失标记处理')
    redeem = pd.to_datetime(clients.first_redeem_date, errors='coerce')
    issue = pd.to_datetime(clients.first_issue_date, errors='coerce')
    check('clients.first_redeem_after_history_end', (redeem > date_max).sum(), '历史窗口末日仅为候选截止点，不能据此认定真实触达日')
    check('clients.first_issue_after_history_end', (issue > date_max).sum())
    check('clients.redeem_before_issue', (redeem < issue).sum())

    fatal = [x for x in checks if x['status']=='ERROR']
    if fatal:
        raise RuntimeError(f'Blocking integrity checks failed: {fatal}; inspect source data before splitting')
    assignments = split_clients(train, args.seed)
    assert assignments.client_id.is_unique and set(assignments.client_id)==train_ids
    export(assignments, output_path(out, 'split_assignments.csv'))
    stratified = train.merge(assignments, on='client_id', validate='one_to_one')
    # Audit counts only; do not publish holdout outcome metrics or inspect holdout for model design.
    split_summary = stratified.groupby('split').size().rename('customers').reset_index()
    split_summary.to_csv(output_path(out, 'split_summary.csv'), index=False, encoding='utf-8-sig')
    dev_counts = stratified[stratified.split!='holdout'].groupby(['split','treatment_flg','target']).size().rename('customers').reset_index()
    dev_counts.to_csv(output_path(out, 'development_strata_counts.csv'), index=False, encoding='utf-8-sig')
    for name,frame in tables.items():
        files.append(dict(table=name, rows=len(frame), columns=len(frame.columns), bytes=(data/f'{name}.csv').stat().st_size))
    files.append(dict(table='purchases', rows=row_count, columns=len(purchase_columns), bytes=(data/'purchases.csv').stat().st_size))
    for name,cols in [(n,list(f.columns)) for n,f in tables.items()] + [('purchases',purchase_columns)]:
        for col in cols:
            meaning = MEANINGS.get(col)
            if meaning is None:
                meaning = ('商品分类层级编号' if col.startswith('level_') else
                           '积分字段；收取/使用方向按字段名区分，正负号及业务口径使用前进一步核对' if 'points' in col else
                           '维度编号；字符串读取，避免误当连续变量' if col.endswith('_id') else '待核对业务定义')
            dictionary.append(dict(table=name,field=col,read_dtype='string',meaning=meaning,
                                   feature_policy=('treatment_indicator_for_grouping_or_counterfactual_input' if col=='treatment_flg' else
                                                   'label_only' if col in ['target','uplift'] else 'verify_pre_contact_availability')))
    export(files,output_path(out, 'table_summary.csv'))
    export(profiles,output_path(out, 'field_profile.csv'))
    export(numeric,output_path(out, 'numeric_and_date_ranges.csv'))
    export(dictionary,output_path(out, 'data_dictionary.csv'))
    export(checks,output_path(out, 'quality_checks.csv'))
    metadata = dict(generated_utc=datetime.now(timezone.utc).isoformat(), python=sys.version,
                    executable=sys.executable, pandas=pd.__version__, numpy=np.__version__, platform=platform.platform(),
                    seed=args.seed, split_method='SHA256(seed:client_id) ordered within treatment x target strata; 60/20/20',
                    chunk_size=args.chunk_size, elapsed_seconds=round(time.time()-start,2), files=files,
                    transactions=tx_count, multiline_transactions=repeated,
                    distinct_purchase_clients=len(observed_users), distinct_purchase_products=len(observed_products),
                    history_start=str(date_min), history_end=str(date_max),
                    purchase_rows_duplicates_scope='within_chunk_only', checks=checks)
    (output_path(out, 'audit_summary.json')).write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    db.close()
    db_path.unlink()
    warnings = [x for x in checks if x['status']=='WARNING']
    report = ['# X5 第一阶段：数据检查与评价设计', '',
              '本阶段全量扫描六张 CSV。原始文件未修改。未训练模型，未估计营销收益，未计算最终保留集效果。', '',
              '## 数据规模', '', '| 表 | 行数 | 字段数 |', '|---|---:|---:|']
    report += [f"| {f['table']} | {f['rows']:,} | {f['columns']} |" for f in files]
    report += ['', '## 已核实的关键事实', '',
               f'- 历史购买时间：{date_min} 至 {date_max}。原始时区未注明。',
               f'- 购买明细含 {tx_count:,} 笔客户级交易（客户编号＋交易编号），其中 {repeated:,} 笔包含多行。',
               '- 原始行是交易中的商品明细，不是一行一笔订单。purchase_sum 的交易内一致性已全量检查；计算消费金额须先在交易级去重，不能直接对商品行累计。',
               '- 客户＋交易编号组合键内时间、门店和 purchase_sum 的一致性，以及客户/商品关联完整性，见 tables/quality_checks.csv。', '',
               '## 待处理问题', '']
    report += [f"- {x['check']}：{x['issue_count']:,}。{x['note']}" for x in warnings]
    report += ['', '字段缺失明细见 tables/field_profile.csv；结构性缺失与真实异常须分开解释，不自动填零或删除。', '',
               '## 固定划分与防泄漏', '',
               f'- 随机种子标识：{args.seed}。按 treatment_flg × target 分层，以 SHA256(seed:client_id) 稳定排序后按 60%/20%/20% 分配。',
               '- splits/split_assignments.csv 仅保存 client_id 和 train/validation/holdout。客户互斥且完整覆盖全部有标签客户。',
               '- 分层划分使用结果标签属于抽样设计，不属于预测特征。holdout 仅显示人数，不发布其转化率或模型指标。',
               '- train 用于探索、特征设计和拟合；validation 用于调参与策略选择；holdout 仅在模型和策略锁定后最终评价。',
               '- 官方 uplift_test 无结果标签，与本地 holdout 不同；其样例分数不是标签。',
               '- 未提供精确营销触达日和用户属性快照时间。购买表按任务说明视为触达前历史，但尚不能仅凭日志末日证明真实触达时点。',
               '- 后续可把历史末日后一日作为 RFM 的分析参考日，明确其为假设；不能称其为已核实的触达日。',
               '- first_redeem_date、年龄等属性必须核对预测时刻可用性；晚于截止时间的日期不得直接使用。', '',
               '## 下一阶段', '',
               '先在 train 客户上完成客户分析与特征设计。构建交易级表，再计算 RFM、客单价、复购间隔和品类偏好。无历史客户保留并标记；不把客户首次观察购买当作真实首次购买。',
               'Cohort 使用观察窗口内首次购买月份定义，标注左截断及右删失。营销总体效应与异质性分析在后续阶段完成。', '',
               '详细指标定义见 ../../docs/metric_dictionary.md，运行方法见项目 README.md。', '']
    (output_path(out, '数据检查报告.md')).write_text('\n'.join(report),encoding='utf-8')
    print(json.dumps({k:metadata[k] for k in ['elapsed_seconds','transactions','history_start','history_end']},ensure_ascii=False),flush=True)


if __name__ == '__main__':
    main()
