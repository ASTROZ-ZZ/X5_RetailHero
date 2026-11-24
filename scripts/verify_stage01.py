#!/usr/bin/env python3
"""Validate audit deliverables, customer partitions and input fingerprints."""
from pathlib import Path
from stage01_layout import output_path
import csv
import hashlib
import json
import sys
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results' / '01_data_audit'


def records(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def main():
    summary = json.loads((output_path(OUT, 'audit_summary.json')).read_text())
    assert not [c for c in summary['checks'] if c['status']=='ERROR']
    source = records(ROOT/'data/uplift_train.csv')
    assignments = records(output_path(OUT, 'split_assignments.csv'))
    ids = [r['client_id'] for r in assignments]
    assert len(ids) == len(set(ids)) == len(source)
    assert set(ids) == {r['client_id'] for r in source}
    assert {r['split'] for r in assignments} == {'train','validation','holdout'}
    source_ids = {r['client_id'] for r in records(ROOT/'data/uplift_test.csv')}
    assert not (source_ids & set(ids))
    counts = {r['split']: int(r['customers']) for r in records(output_path(OUT, 'split_summary.csv'))}
    assert sum(counts.values()) == len(source)
    for name, n in counts.items():
        assert sum(r['split']==name for r in assignments) == n
    # Regenerate from reversed source order, proving that source ordering cannot change assignments.
    spec = importlib.util.spec_from_file_location('audit_stage01', ROOT/'scripts/01_audit_data.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source_frame = module.pd.DataFrame(source)
    rebuilt = module.split_clients(source_frame.iloc[::-1], summary['seed'])
    assert rebuilt.to_dict('records') == assignments
    rows = {r['table']: int(r['rows']) for r in records(output_path(OUT, 'table_summary.csv'))}
    assert sum(int(r['purchase_rows']) for r in records(output_path(OUT, 'monthly_purchase_rows.csv'))) == rows['purchases']
    fields = records(output_path(OUT, 'field_profile.csv'))
    for r in fields:
        assert int(r['rows']) == rows[r['table']]
        assert 0 <= int(r['missing']) <= int(r['rows'])
    dictionary = records(output_path(OUT, 'data_dictionary.csv'))
    fingerprints = []
    for p in sorted((ROOT/'data').glob('*.csv')):
        with p.open(newline='') as f:
            header = next(csv.reader(f))
        assert header == [r['field'] for r in dictionary if r['table']==p.stem]
        digest = hashlib.sha256()
        with p.open('rb') as f:
            for block in iter(lambda: f.read(8*1024*1024), b''):
                digest.update(block)
        fingerprints.append(dict(file=p.name,bytes=p.stat().st_size,sha256=digest.hexdigest()))
        print(f'fingerprinted {p.name}',flush=True)
    result = dict(status='PASS',checks=['no_blocking_integrity_error','complete_unique_customer_partition',
                  'official_test_disjoint','split_counts_reconciled','split_independent_of_input_order','monthly_rows_reconciled',
                  'missing_counts_bounded','dictionary_matches_headers'],split_counts=counts,
                  input_fingerprints=fingerprints)
    (output_path(OUT, 'verification.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
