#!/usr/bin/env python3
"""Build X5 training orders and analyze historical customer behavior."""

import argparse
from contextlib import closing
import gzip
import hashlib
import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
STAGE01 = ROOT / "results/01_data_audit"
DEFAULT_OUT = ROOT / "results/02_customer_analysis"
UNKNOWN = "__UNKNOWN__"
SEGMENTS = ["高价值活跃", "高价值待唤醒", "近期活跃", "低近期活跃", "其他客户"]
KEY = ["client_id", "transaction_id"]
PURCHASE_COLUMNS = KEY + [
    "transaction_datetime", "store_id", "purchase_sum", "product_id", "product_quantity"
]


def save(frame, path):
    frame.to_csv(path, index=False, encoding="utf-8-sig")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_inputs(split="train"):
    split_path = STAGE01 / "splits/split_assignments.csv"
    assignments = pd.read_csv(split_path, dtype=str)
    require(assignments.client_id.is_unique, "Duplicate customer in fixed split")
    ids = pd.Index(assignments.loc[assignments.split.eq(split), "client_id"].sort_values())
    require(len(ids) > 0, f"The fixed {split} split is empty")

    product = pd.read_csv(
        ROOT / "data/products.csv", usecols=["product_id", "level_2"], dtype=str
    ).set_index("product_id", verify_integrity=True)["level_2"].fillna(UNKNOWN)
    codes = pd.Index(sorted(set(product) - {UNKNOWN}) + [UNKNOWN], name="level_2")
    product_code = pd.Series(codes.get_indexer(product), index=product.index)

    audit = json.loads((STAGE01 / "metadata/audit_summary.json").read_text(encoding="utf-8"))
    return ids, codes, product_code, audit, hashlib.sha256(split_path.read_bytes()).hexdigest()


def build_orders(db, ids, codes, product_code, chunk_size, start, end):
    db.executescript("""
        PRAGMA journal_mode=OFF;
        PRAGMA synchronous=OFF;
        CREATE TABLE orders (
            client_id TEXT NOT NULL, transaction_id TEXT NOT NULL,
            transaction_datetime TEXT NOT NULL, store_id TEXT NOT NULL,
            purchase_cents INTEGER NOT NULL, line_count INTEGER NOT NULL,
            conflict INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (client_id, transaction_id)
        ) WITHOUT ROWID;
    """)
    insert = """
        INSERT INTO orders (client_id,transaction_id,transaction_datetime,store_id,purchase_cents,line_count)
        VALUES (?,?,?,?,?,?)
        ON CONFLICT(client_id,transaction_id) DO UPDATE SET
            line_count=orders.line_count+excluded.line_count,
            conflict=orders.conflict OR
                orders.transaction_datetime<>excluded.transaction_datetime OR
                orders.store_id<>excluded.store_id OR orders.purchase_cents<>excluded.purchase_cents
    """
    id_code = pd.Series(np.arange(len(ids)), index=ids)
    line_counts = np.zeros((len(ids), len(codes)), dtype=np.int64)
    quantities = np.zeros_like(line_counts, dtype=np.float64)
    scanned = selected = zero_quantity = 0
    dtypes = {c: str for c in PURCHASE_COLUMNS}
    for batch, chunk in enumerate(pd.read_csv(
        ROOT / "data/purchases.csv", chunksize=chunk_size, usecols=PURCHASE_COLUMNS, dtype=dtypes
    ), start=1):
        scanned += len(chunk)
        chunk = chunk.loc[chunk.client_id.isin(ids)].copy()
        if len(chunk):
            selected += len(chunk)
            require(chunk.notna().all().all(), "Selected purchase row has a missing required field")
            require(chunk.transaction_datetime.between(start, end).all(), "Purchase outside audited time range")
            amount = pd.to_numeric(chunk.purchase_sum).to_numpy() * 100
            cents = np.rint(amount)
            require(np.isfinite(amount).all() and np.allclose(amount, cents, rtol=0, atol=1e-6),
                    "Order amount is not representable to two decimal places")
            chunk["purchase_cents"] = cents.astype(np.int64)

            product_positions = chunk.product_id.map(product_code)
            require(product_positions.notna().all(), "Unmatched product in training purchases")
            row_positions = chunk.client_id.map(id_code).to_numpy(dtype=np.intp)
            col_positions = product_positions.to_numpy(dtype=np.intp)
            quantity = pd.to_numeric(chunk.product_quantity).to_numpy()
            require(np.isfinite(quantity).all() and (quantity >= 0).all(), "Invalid product quantity")
            zero_quantity += int(np.count_nonzero(quantity == 0))
            np.add.at(line_counts, (row_positions, col_positions), 1)
            np.add.at(quantities, (row_positions, col_positions), quantity)

            order_cols = KEY + ["transaction_datetime", "store_id", "purchase_cents"]
            grouped = chunk.groupby(order_cols, sort=False).size().reset_index(name="line_count")
            db.executemany(insert, grouped.itertuples(index=False, name=None))
            db.commit()
        if batch == 1 or batch % 10 == 0:
            print(f"Scanned {scanned:,} purchase rows; selected {selected:,}", flush=True)

    require(not db.execute("SELECT 1 FROM orders WHERE conflict LIMIT 1").fetchone(),
            "Conflicting metadata within a customer order")
    count, lines, cents = db.execute(
        "SELECT count(*), sum(line_count), sum(purchase_cents) FROM orders"
    ).fetchone()
    require(lines == selected == int(line_counts.sum()), "Purchase rows do not reconcile")
    return line_counts, quantities, dict(
        rows_scanned=scanned, training_purchase_lines=selected, training_orders=count,
        training_purchase_cents=cents, zero_quantity_lines=zero_quantity
    )


def summarize_customers(db, ids, reference, thresholds=None):
    clients = pd.read_sql_query("""
        SELECT client_id, count(*) AS frequency, sum(purchase_cents) AS monetary_cents,
            min(transaction_datetime) AS first_purchase,
            max(transaction_datetime) AS last_purchase
        FROM orders GROUP BY client_id ORDER BY client_id
    """, db).set_index("client_id")
    require(clients.index.equals(ids), "Orders do not cover exactly the selected customers")
    coverage = pd.read_csv(STAGE01 / "tables/client_history_coverage.csv", dtype=str).set_index("client_id").loc[ids]
    require(np.array_equal(clients.frequency, coverage.transactions.astype(int)) and
            np.array_equal(clients.first_purchase, coverage.first_purchase) and
            np.array_equal(clients.last_purchase, coverage.last_purchase),
            "Order counts or endpoints differ from the stage 01 customer audit")
    clients["recency_days"] = (reference - pd.to_datetime(clients.last_purchase).dt.normalize()).dt.days
    clients["monetary"] = clients.monetary_cents / 100
    clients["avg_order_value"] = clients.monetary / clients.frequency

    days = pd.read_sql_query("""
        SELECT client_id, substr(transaction_datetime,1,10) AS purchase_day
        FROM orders GROUP BY client_id, purchase_day ORDER BY client_id, purchase_day
    """, db)
    days["purchase_day"] = pd.to_datetime(days.purchase_day)
    grouped = days.groupby("client_id", sort=False)
    clients["purchase_days"] = grouped.size()
    days["gap"] = grouped.purchase_day.diff().dt.days
    clients["median_repurchase_gap_days"] = days.groupby("client_id", sort=False).gap.median()
    clients["cohort_month"] = clients.first_purchase.str.slice(0, 7)
    clients["segment"], thresholds = assign_segments(clients, thresholds)
    return clients, days, thresholds


def assign_segments(clients, thresholds=None):
    if thresholds is None:
        thresholds = {
            "frequency_q75": int(clients.frequency.quantile(.75, interpolation="higher")),
            "monetary_cents_q75": int(clients.monetary_cents.quantile(.75, interpolation="higher")),
            "recency_q25": int(clients.recency_days.quantile(.25, interpolation="higher")),
            "recency_q75": int(clients.recency_days.quantile(.75, interpolation="higher")),
        }
    high = clients.frequency.ge(thresholds["frequency_q75"]) & clients.monetary_cents.ge(
        thresholds["monetary_cents_q75"]
    )
    dormant = clients.recency_days.ge(thresholds["recency_q75"])
    recent = clients.recency_days.le(thresholds["recency_q25"])
    segment = np.select([high & dormant, high, dormant, recent],
                        ["高价值待唤醒", "高价值活跃", "低近期活跃", "近期活跃"], default="其他客户")
    return segment, thresholds


def category_results(clients, codes, lines, qty):
    totals = lines.sum(axis=1)
    known = lines[:, :-1]
    top = known.argmax(axis=1)
    top_lines = known.max(axis=1)
    clients["top_level_2_by_lines"] = codes.take(top).where(top_lines > 0, pd.NA)
    clients["top_level_2_line_share"] = np.divide(top_lines, totals)
    clients["distinct_known_level_2"] = np.count_nonzero(known, axis=1)

    results = []
    for segment in ["全部训练客户", *SEGMENTS]:
        mask = np.ones(len(clients), dtype=bool) if segment == "全部训练客户" else clients.segment.eq(segment).to_numpy()
        c_lines, c_qty = lines[mask], qty[mask]
        n_lines, n_qty = c_lines.sum(axis=0), c_qty.sum(axis=0)
        results.append(pd.DataFrame({
            "segment": segment, "level_2": codes, "customers_in_segment": int(mask.sum()),
            "customers_with_category": np.count_nonzero(c_lines, axis=0),
            "line_count": n_lines, "line_share": n_lines / max(n_lines.sum(), 1),
            "positive_quantity": n_qty,
            "quantity_share": n_qty / n_qty.sum() if n_qty.sum() else np.nan,
        }).sort_values(["line_count", "level_2"], ascending=[False, True]))
    return pd.concat(results, ignore_index=True)


def cohort_results(clients, days, start, end):
    start_date, end_date = pd.Timestamp(start), pd.Timestamp(end)
    start_month, end_month = start_date.to_period("M"), end_date.to_period("M")
    activity = days.assign(active_month=days.purchase_day.dt.to_period("M"))
    activity = activity[["client_id", "active_month"]].drop_duplicates()
    activity["cohort_month"] = activity.client_id.map(clients.cohort_month)
    active = activity.groupby(["cohort_month", "active_month"]).size()
    results = []
    for cohort, n in clients.cohort_month.value_counts().sort_index().items():
        first = pd.Period(cohort, freq="M")
        for offset in range(end_month.ordinal - start_month.ordinal + 1):
            month = first + offset
            complete_cohort = first != start_month and first != end_month
            complete_month = start_month < month < end_month
            count = int(active.get((cohort, month), 0)) if month <= end_month else None
            if count is None:
                status = "outside_observation"
            elif not complete_month:
                status = "partial_activity_month"
            elif not complete_cohort:
                status = "partial_cohort_month"
            else:
                status = "complete"
            results.append(dict(
                cohort_month=cohort, month_offset=offset, activity_month=str(month),
                cohort_customers=int(n), active_customers_observed=count,
                cohort_month_complete=complete_cohort, status=status,
                repeat_rate=count / n if status == "complete" else None,
            ))
    return pd.DataFrame(results)


def export_orders(db, path):
    rows = 0
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        for block in pd.read_sql_query("""
            SELECT client_id, transaction_id, transaction_datetime, store_id, purchase_cents, line_count
            FROM orders ORDER BY client_id, transaction_id
        """, db, chunksize=200_000):
            block["purchase_sum"] = block.pop("purchase_cents") / 100
            block.to_csv(handle, index=False, header=rows == 0, float_format="%.2f")
            rows += len(block)
    return rows


def segment_summary(clients):
    result = clients.groupby("segment").agg(
        customers=("client_id", "size"), orders=("frequency", "sum"),
        sales=("monetary", "sum"), median_recency_days=("recency_days", "median"),
        median_frequency=("frequency", "median"), median_monetary=("monetary", "median"),
        median_customer_aov=("avg_order_value", "median"),
        customers_with_gap=("median_repurchase_gap_days", "count"),
        median_customer_gap_days=("median_repurchase_gap_days", "median"),
    ).reindex(SEGMENTS)
    result["customer_share"] = result.customers / len(clients)
    result["sales_share"] = result.sales / result.sales.sum()
    result["order_weighted_aov"] = result.sales / result.orders
    return result.reset_index()


def write_report(path, stats, clients, segments, categories, cohort, thresholds):
    overall = categories[categories.segment.eq("全部训练客户") & categories.level_2.ne(UNKNOWN)]
    top_lines = overall.iloc[0]
    top_qty = overall.sort_values(["positive_quantity", "level_2"], ascending=[False, True]).iloc[0]
    high = segments.iloc[:2]
    gap_n = int(clients.median_repurchase_gap_days.notna().sum())
    feb = cohort[(cohort.cohort_month == "2019-01") & (cohort.activity_month == "2019-02")].iloc[0]
    report = [
        "# X5 客户消费分析", "",
        f"在 {len(clients):,} 位固定训练客户中，共识别出 {stats['training_orders']:,} 笔历史订单。",
        f"同时达到频次和消费额上四分位阈值的客户占 {high.customer_share.sum():.1%}，贡献了历史消费额的 {high.sales_share.sum():.1%}。",
        "", "## 订单与客户消费", "",
        f"- 历史窗口为 {stats['history_start']} 至 {stats['history_end']}。RFM 参考日为 {stats['reference_date']}，取历史窗口结束后的第一天。",
        f"- 订单总额 {stats['training_purchase_cents']/100:,.2f}，订单加权客单价 {stats['training_purchase_cents']/100/stats['training_orders']:,.2f}。金额沿用源数据单位。",
        f"- 客户中位数为 {clients.recency_days.median():.0f} 天未购买、{clients.frequency.median():.0f} 笔历史订单、累计消费 {clients.monetary.median():,.2f}，个人客单价中位数为 {clients.avg_order_value.median():,.2f}。",
        f"- {gap_n:,} 位客户至少在两个不同日期购买，可以估计观察期内复购间隔。先取每位客户相邻购买日间隔的中位数，再跨客户取中位数，得到 {clients.median_repurchase_gap_days.median():.1f} 天。其余 {len(clients)-gap_n:,} 位客户的间隔留空。",
        "", "## RFM 分群", "",
        f"高价值门槛为至少 {thresholds['frequency_q75']} 笔订单且累计消费至少 {thresholds['monetary_cents_q75']/100:,.2f}。",
        f"距末次购买至少 {thresholds['recency_q75']} 天归入低近期活跃一侧，其余客户中距末次购买至多 {thresholds['recency_q25']} 天归入近期活跃。先判高价值，再判低近期活跃、近期活跃和其他客户。阈值并列一并纳入。",
        "", "| 客群 | 客户数 | 客户占比 | 消费额占比 | 末次购买间隔中位数 |",
        "|---|---:|---:|---:|---:|",
    ]
    report += [
        f"| {r.segment} | {r.customers:,} | {r.customer_share:.1%} | {r.sales_share:.1%} | {r.median_recency_days:.0f} 天 |"
        for r in segments.itertuples()
    ]
    report += [
        "", "## 品类偏好", "",
        f"- 按商品明细行数，排名第一的二级品类编号为 `{top_lines.level_2}`，占全部商品明细的 {top_lines.line_share:.1%}。按正数量汇总的第一名为 `{top_qty.level_2}`，占总记录数量的 {top_qty.quantity_share:.1%}。",
        f"- 训练集中有 {stats['zero_quantity_lines']:,} 条零数量明细，占 {stats['zero_quantity_lines']/stats['training_purchase_lines']:.2%}。这些行参与出现频次统计，对数量汇总贡献为零。品类编号经过匿名化，数量口径用于对照排名。",
        "- 品类表同时给出各客群的总行数份额、数量份额和购买该类的客户数。分母包含分类未知的明细。个人首选品类只在已知编号中按行数选，平局按编号排序。",
        "", "## 月度 Cohort", "",
        f"以每位客户在本窗口内第一次观察到的购买月份分组。2019 年 1 月组有 {int(feb.cohort_customers):,} 位客户，其中 {int(feb.active_customers_observed):,} 位在 2 月购买，占 {feb.repeat_rate:.1%}。",
        "11 月和 3 月只覆盖部分月份。部分月或窗口外月份不发布整月复购率。首次观察月份受历史窗口左边界影响，不能据此判断客户何时首次成为会员。",
        "", "## 验证与使用范围", "",
        f"本次从全量明细中筛出 {stats['training_purchase_lines']:,} 条训练商品行。订单数量、首次和末次购买时间逐客户与第一阶段一致，订单金额、客户累计金额与输出订单数均已核对。",
        "画像、分层和 Cohort 描述固定训练集的历史行为。历史高消费客群可以作为后续短信实验的预设分层，是否对短信更敏感需要实验数据验证。",
        "", "复现代码和数据表见 [结果索引](README.md)。", "",
    ]
    path.write_text("\n".join(report), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunk-size", type=int, default=500_000)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    if args.chunk_size <= 0:
        parser.error("--chunk-size must be positive")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / "tables").mkdir(exist_ok=True)
    (out / "metadata").mkdir(exist_ok=True)
    ids, codes, product, audit, split_hash = read_inputs()
    start, end = audit["history_start"], audit["history_end"]
    reference = pd.Timestamp(end).normalize() + pd.Timedelta(days=1)
    with TemporaryDirectory(prefix=".customer_analysis-", dir=out) as tmp, closing(
        sqlite3.connect(Path(tmp) / "orders.sqlite")
    ) as db:
        line_counts, qty, stats = build_orders(db, ids, codes, product, args.chunk_size, start, end)
        expected = next(f["rows"] for f in audit["files"] if f["table"] == "purchases")
        require(stats["rows_scanned"] == expected, "Full purchase row count differs from stage 01")
        print("Reconciling customer history and calculating RFM and Cohort", flush=True)
        clients, days, thresholds = summarize_customers(db, ids, reference)
        categories = category_results(clients, codes, line_counts, qty)
        cohort = cohort_results(clients, days, start, end)
        clients = clients.reset_index()
        require(int(clients.monetary_cents.sum()) == stats["training_purchase_cents"],
                "Customer monetary total differs from order total")
        require(int(clients.frequency.sum()) == stats["training_orders"], "Customer order count differs")
        segments = segment_summary(clients)
        monetary = clients[["recency_days", "frequency", "monetary", "avg_order_value",
                           "purchase_days", "median_repurchase_gap_days"]]
        profile = monetary.describe(percentiles=[.1, .25, .5, .75, .9, .95, .99]).T
        profile.index.name = "metric"
        stage = Path(tmp)
        files = {
            "training_orders.csv.gz": "tables",
            "customer_features.csv": "tables",
            "segment_summary.csv": "tables",
            "customer_metric_distribution.csv": "tables",
            "category_preferences.csv": "tables",
            "cohort_repeat.csv": "tables",
            "analysis_summary.json": "metadata",
            "客户消费分析报告.md": "",
        }
        print("Writing training orders and analysis outputs", flush=True)
        require(export_orders(db, stage / "training_orders.csv.gz") == stats["training_orders"],
                "Exported order count differs from source")
        save(clients.drop(columns="monetary_cents"), stage / "customer_features.csv")
        save(segments, stage / "segment_summary.csv")
        save(profile.reset_index(), stage / "customer_metric_distribution.csv")
        save(categories, stage / "category_preferences.csv")
        save(cohort, stage / "cohort_repeat.csv")
        stats.update(
            status="PASS", history_start=start, history_end=end, reference_date=str(reference.date()),
            training_customers=len(ids), split_file_sha256=split_hash, thresholds=thresholds,
            pandas=pd.__version__, numpy=np.__version__,
            checks=["fixed_training_population", "orders_unique_and_consistent", "raw_rows_reconciled",
                    "customer_order_count_and_endpoints_match_stage01", "customer_amount_matches_order_amount",
                    "exported_order_count_matches"],
        )
        (stage / "analysis_summary.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
        write_report(stage / "客户消费分析报告.md", stats, clients, segments, categories, cohort, thresholds)
        for name, directory in files.items():
            (stage / name).replace(out / directory / name)
    print(json.dumps(stats, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
