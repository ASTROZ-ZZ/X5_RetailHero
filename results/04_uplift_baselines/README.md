# 第四阶段 · Uplift 基线与验证

用 120,022 位训练客户拟合模型和预处理。在相同的 40,008 位验证客户上比较六种排序。主要指标为前 30% 人群中短信组与对照组购买率之差。

| 文件 | 内容 |
|---|---|
| [Uplift 基线验证报告](Uplift基线验证报告.md) | 候选模型、基线差异与解读边界 |
| [验证集特征](tables/validation_features.csv) | 复用第二阶段购买历史、RFM 和品类口径 |
| [前 30% 策略对照](tables/validation_at30.csv) | 每种排序的购买率差、区间、样本量、AUUC 和 Qini |
| [覆盖比例明细](tables/validation_curves.csv) | 从 5% 到 100% 的逐点购买率差和累计增量 |
| [候选与基线对比](tables/candidate_vs_baselines.csv) | 考虑名单重叠的配对置信区间 |
| [验证集分数](tables/validation_scores.csv.gz) | 每位验证客户的六种策略分数，可复算排序 |
| [模型配置及候选](metadata/baseline_summary.json) | 特征、种子、超参数、模型候选和运行版本 |
| [验证结果](metadata/verification.json) | 依据保存分数和原始实验标签独立复算的检查 |
| [策略对照图](figures/validation_uplift.png) | 前 30% 排序结果及逐项置信区间 |

在 X5 项目根目录运行以下命令。验证特征已生成时，可直接运行第二条。

```bash
python scripts/04_build_validation_features.py
python scripts/04_uplift_baselines.py
python scripts/plot_stage04.py
```

本次建模复现环境使用 Python 3.12、NumPy 1.26.4、pandas 2.2.3、SciPy 1.13.1 和 scikit-learn 1.6.1。绘图使用 Matplotlib 3.11.2。训练集和验证集保持固定，最终保留集用于后续独立验证。
