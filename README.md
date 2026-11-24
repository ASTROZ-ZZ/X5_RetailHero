# X5 RetailHero：零售客户分析与短信营销增量优化

当前进度：离线预测与项目总结已交付。最终保留集上，T-Learner 逻辑回归优于 RFM，尚未确认它相对随机排序的优势。

优化诊断已完成。新增购买节奏特征的平均改善很小，当前离线交付沿用原 T-Learner。

## 阅读入口

- [企业决策报告 PDF](results/reporting/X5_RetailHero_企业决策报告.pdf) · [可编辑 Word 版](results/reporting/X5_RetailHero_企业决策报告.docx)
- [数据分析作品集](results/reporting/X5_RetailHero_数据分析作品集.pdf)
- [六张原始数据的完整分卷备份与还原方法](data/backup/README.md)

- [任务需求](docs/任务需求.md)：目标、评分与交付要求。
- [第一阶段报告](results/01_data_audit/数据检查报告.md)：当前发现与处理建议。
- [第二阶段客户分析](results/02_customer_analysis/README.md)：订单表、RFM、复购、品类偏好和 Cohort。
- [第三阶段短信实验](results/03_sms_experiment/README.md)：组间平衡、总体购买率差、分群差异和置信区间图。
- [第四阶段 Uplift 基线](results/04_uplift_baselines/README.md)：策略比较、验证结果和复现方法。
- [第五阶段最终保留集](results/05_holdout_evaluation/README.md)：锁定的候选、独立评估和策略采用门槛。
- [第六阶段离线交付](results/06_offline_delivery/README.md)：官方测试预测、独立核验和项目总结。
- [第七阶段优化诊断](results/07_uplift_optimization/README.md)：购买节奏特征、重复交叉验证和候选对比。
- [指标字典](docs/metric_dictionary.md)：统计口径与防泄漏约束。
- [数据来源](docs/sources/README.md)：当前文件状态与历史下载资料。

## 目录

```text
X5_RetailHero/
├── README.md                  项目入口
├── requirements.txt           Python 依赖
├── data/backup/               六张原始 CSV 的无损分卷备份
├── docs/                      任务与指标
│   └── sources/               下载清单与来源原件
├── scripts/                   日常执行代码
│   └── archive/               历史修复脚本
└── results/
    └── 01_data_audit/
        ├── README.md          本阶段文件索引
        ├── 数据检查报告.md    优先阅读
        ├── tables/            字段、质量与统计表
        ├── splits/            固定客户划分及汇总
        ├── metadata/          运行摘要与验证结果
        └── logs/              运行与验证日志
```

第二阶段结果在 `results/02_customer_analysis/`。运行方式及各表说明见该阶段的索引。

## 运行

在本项目目录下执行，需要 Python 3.11+，依赖见 `requirements.txt`：

```bash
python scripts/01_audit_data.py
python scripts/verify_stage01.py
```

首次克隆仓库后，先还原原始数据，再安装依赖并运行分析。六张 CSV 已压缩分卷保存到仓库，下载完整仓库后可在本机恢复。

```bash
python scripts/restore_source_data.py
python -m pip install -r requirements.txt
```

全量审计按批读取约 4.46 GB 购买明细，用临时 SQLite 检查跨批交易一致性，需数 GB 空闲磁盘。结束后删除临时数据库。默认覆盖本阶段同名结果；只需核对已有结果时运行验证脚本即可。

```bash
python scripts/01_audit_data.py --chunk-size 250000 --output results/01_data_audit_rerun
```

自定义目录可另存审计结果；验证脚本默认检查正式目录。输出位置由 `scripts/stage01_layout.py` 统一管理，重新运行仍按子目录分类。

## 关键约束

- 原始 CSV 在 `data/`，ID 按字符串读取。
- 订单键为 `(client_id, transaction_id)`；28 个交易编号跨客户复用。整单金额须先在订单粒度去重。
- 固定划分在 `results/01_data_audit/splits/split_assignments.csv`，种子标识 20261116，训练/验证/最终保留集比例约 60/20/20。
- train 用于探索，validation 选择模型与策略，holdout 最后评价。
- 完全重复行只检查批内，不声称跨批无重复；商品分类层级按字符串处理。
- 官方测试无结果标签，本项目为离线复现，不报告排行榜成绩。

历史修复脚本在 `scripts/archive/finalize_stage01.py`，日常无需执行。
