# 第二阶段 · 客户消费分析

从 [客户消费分析报告](客户消费分析报告.md) 开始。分析范围为第一阶段固定的 120,022 位训练客户。

| 文件 | 内容 |
|---|---|
| [training_orders.csv.gz](tables/training_orders.csv.gz) | 每笔订单一行，按客户和交易编号排序。含交易时间、门店、整单金额和明细行数。可直接用 pandas 读取。 |
| [customer_features.csv](tables/customer_features.csv) | 每位训练客户一行，含 RFM、客单价、购买天数、复购间隔、分群、观察期 Cohort 和首选二级品类。 |
| [customer_metric_distribution.csv](tables/customer_metric_distribution.csv) | 值域、均值、标准差和关键分位数，用于查看客户消费分布。 |
| [segment_summary.csv](tables/segment_summary.csv) | 五个客群的人数、历史消费贡献、客单价和复购统计。 |
| [category_preferences.csv](tables/category_preferences.csv) | 全体及分群的二级品类明细行份额、正数量份额和客户数。未知分类标为 `__UNKNOWN__`。 |
| [cohort_repeat.csv](tables/cohort_repeat.csv) | 首次观察购买月与后续月的活动人数。部分月和窗口外月份的整月复购率留空。 |
| [analysis_summary.json](metadata/analysis_summary.json) | 样本规模、输入划分指纹、分群阈值和程序内核对结果。 |
| [verification.json](metadata/verification.json) | 从导出的订单及客户表独立核对笔数、金额、客户覆盖和 Cohort 状态的结果。 |
| [客群消费贡献图](figures/rfm_segment_share.png) · [Cohort 活跃图](figures/cohort_purchase_activity.png) | 由结果表生成的图表。 |

运行和验证记录在 `logs/`。详细统计口径见 [指标字典](../../docs/metric_dictionary.md)。

## 复现

在 X5 项目目录中执行，依赖见根目录的 `requirements.txt`。

```bash
python scripts/02_customer_analysis.py
python scripts/verify_stage02.py
```

分析代码分批读取全量购买明细，在临时 SQLite 中合并训练客户的订单。本次约 4.46 GB 输入，建议预留数 GB 空间。结果默认写入当前阶段目录，可用 `--output` 另存。复现 PNG 需使用含 Matplotlib 的 Python 环境，本次使用 3.11.2。

```bash
python scripts/plot_stage02.py
```

用 Python 读取订单表时声明 ID 列为字符串，以保留前导零。

```python
import pandas as pd

orders = pd.read_csv(
    "results/02_customer_analysis/tables/training_orders.csv.gz",
    dtype={"client_id": str, "transaction_id": str, "store_id": str},
)
```
