"""Paths for stage 01 outputs. Filenames and result contents remain stable."""
from pathlib import Path

LAYOUT = {'quality_checks.csv': 'tables/quality_checks.csv', 'purchase_time_range.csv': 'tables/purchase_time_range.csv', 'table_summary.csv': 'tables/table_summary.csv', 'gender_counts.csv': 'tables/gender_counts.csv', 'monthly_purchase_rows.csv': 'tables/monthly_purchase_rows.csv', 'client_history_coverage.csv': 'tables/client_history_coverage.csv', 'field_profile.csv': 'tables/field_profile.csv', 'numeric_and_date_ranges.csv': 'tables/numeric_and_date_ranges.csv', 'data_dictionary.csv': 'tables/data_dictionary.csv', 'split_assignments.csv': 'splits/split_assignments.csv', 'split_summary.csv': 'splits/split_summary.csv', 'development_strata_counts.csv': 'splits/development_strata_counts.csv', 'audit_summary.json': 'metadata/audit_summary.json', 'verification.json': 'metadata/verification.json', 'run.log': 'logs/run.log', 'verification.log': 'logs/verification.log'}

def output_path(base, filename):
    path = Path(base) / LAYOUT.get(filename, filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
