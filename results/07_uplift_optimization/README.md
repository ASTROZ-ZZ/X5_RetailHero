# 第七阶段 · Uplift 优化诊断

[优化诊断报告](Uplift优化诊断报告.md)比较原 T-Learner、加入行为特征的 T-Learner，以及带两个短信交互项的正则化 S-Learner。分析使用原训练集和验证集的 160,030 位客户，采用三次重复五折分层验证。

| 文件 | 内容 |
|---|---|
| [行为特征](tables/behavior_features.csv) | 每位开发客户的相邻 14 天订单数差和相对个人复购间隔。 |
| [模型汇总](tables/model_summary.csv) | 各模型的平均 Uplift、相对随机和原模型的均值差及稳定性。 |
| [按次重复汇总](tables/repeat_summary.csv) · [逐折结果](tables/fold_metrics.csv) | 每次重复及每折上的同样本比较。 |
| [随机基线结果](tables/random_fold_metrics.csv) | 每折 12 个固定种子的实际名单评价。 |
| [折外分数](tables/fold_scores.csv.gz) | 每次重复中每位客户的三种模型分数及所在评估折。 |
| [方案](metadata/cv_plan.json) · [运行摘要](metadata/cv_summary.json) · [核验结果](metadata/verification.json) | 种子、触达规则、运行版本和独立复算记录。 |
| [重复验证图](figures/repeated_cv_uplift.png) | 三种模型在重复验证中的均值。 |

以下命令在 X5 项目目录执行。建模依赖与[第四阶段](../04_uplift_baselines/README.md)相同。已生成行为特征时从第二条开始。

```bash
python scripts/07_build_behavior_features.py
python scripts/07_optimize_uplift.py
python scripts/verify_stage07.py
python scripts/plot_stage07.py
```

用于竞赛格式的预测文件见[第六阶段交付](../06_offline_delivery/README.md)。最终独立评估见[第五阶段](../05_holdout_evaluation/README.md)。
