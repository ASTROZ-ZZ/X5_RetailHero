# 第一阶段：数据检查与固定划分

先读 [数据检查报告](数据检查报告.md)。本次整理只调整结果分类路径。

| 子目录 | 内容 |
|---|---|
| `tables/` | 表规模、字段字典、缺失、数值范围、质量检查、时间范围及客户覆盖 |
| `splits/` | 固定客户划分、划分人数、开发集分层人数 |
| `metadata/` | 运行摘要、独立验证与原始 CSV 指纹 |
| `logs/` | 运行与验证日志 |

常用文件：[字段字典](tables/data_dictionary.csv)、[质量检查](tables/quality_checks.csv)、[客户划分](splits/split_assignments.csv)、[验证结果](metadata/verification.json)。

固定人数：train 120,022、validation 40,008、holdout 40,009。holdout 不用于探索和调参。运行方法见 [项目导航](../../README.md)。
