# 第三阶段 · 短信营销实验分析

[实验分析报告](短信营销实验分析报告.md)汇总固定训练集的短信组与对照组购买差值。

| 结果 | 内容 |
|---|---|
| [购买率与差值](tables/purchase_rate_effects.csv) | 总体及五个 RFM 客群的样本量、购买人数、购买率、差值、95% 置信区间和检验结果。五个分群使用 Holm 校正。 |
| [历史特征平衡](tables/covariate_balance.csv) | 两组的特征均值、缺失数及标准化均值差。 |
| [实验摘要](metadata/experiment_summary.json) | 总体估计、五群联合检验以及两类高价值客户的直接对比。 |
| [置信区间图](figures/sms_effect_forest.png) | 总体和五个客群的购买率差，单位为百分点。 |
| [验证结果](metadata/verification.json) | 依据固定划分、实验标签和历史特征独立复算后的核对记录。 |

从 X5 项目根目录运行。绘图脚本需要 Matplotlib，并复用第二阶段的配色和字体。

```bash
python scripts/03_sms_experiment.py
python scripts/plot_stage03.py
```

两个脚本均支持 `--output`。本次分析沿用第二阶段的五个客群，验证集和最终保留集用于后续策略比较和最终评价。
