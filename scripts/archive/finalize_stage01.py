#!/usr/bin/env python3
"""Refresh legacy audit descriptions after categorical-ID and transaction-key corrections.

The main audit already includes these fixes. This idempotent migration preserves the
completed full scan without rescanning 4.46 GB solely to refresh descriptions.
"""
from pathlib import Path
import json
import pandas as pd
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stage01_layout import output_path

OUT = Path(__file__).resolve().parents[2] / 'results' / '01_data_audit'
obsolete = {f'products.level_{i}.invalid_number' for i in range(1,5)}
checks = pd.read_csv(output_path(OUT, 'quality_checks.csv'), keep_default_na=False)
checks = checks[~checks['check'].isin(obsolete)]
checks.loc[checks['check']=='transaction.id_reused_across_customers','note'] = '全局交易编号存在跨客户复用；采用客户+交易编号组合键，不删除原始记录'
checks.to_csv(output_path(OUT, 'quality_checks.csv'),index=False,encoding='utf-8-sig')
summary = json.loads((output_path(OUT, 'audit_summary.json')).read_text())
summary['checks'] = checks.to_dict('records')
summary['transaction_key'] = ['client_id','transaction_id']
summary['audit_execution_note'] = '全量初查后发现28个全局交易编号跨客户复用，利用完成的交易缓存修复，并再次全量扫描字段、核对交易缓存行数。'
(output_path(OUT, 'audit_summary.json')).write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
dictionary = pd.read_csv(output_path(OUT, 'data_dictionary.csv'),keep_default_na=False)
dictionary.loc[dictionary.field=='transaction_id','meaning']='交易标识；跨客户可能复用，交易键使用 client_id + transaction_id'
dictionary.loc[dictionary.field=='treatment_flg','feature_policy']='treatment_indicator_for_grouping_or_counterfactual_input'
dictionary.to_csv(output_path(OUT, 'data_dictionary.csv'),index=False,encoding='utf-8-sig')
report_path = output_path(OUT, '数据检查报告.md')
lines = report_path.read_text().splitlines()
lines = [line for line in lines if not any(name in line for name in obsolete)]
lines = [line.replace('历史缓存复查发现的全局交易编号碰撞；按客户+交易编号恢复，不删除原始记录',
                     '全局交易编号跨客户复用；采用客户+交易编号组合键，不删除原始记录') for line in lines]
lines = [line.replace('交易编号对应客户、时间、门店和 purchase_sum 的一致性',
                     '客户＋交易编号组合键内时间、门店和 purchase_sum 的一致性') for line in lines]
report_path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('Audit descriptions refreshed. Product hierarchy fields are categorical IDs, not numeric errors.')
