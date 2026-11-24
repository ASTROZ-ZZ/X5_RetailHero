# 第五阶段 · 最终保留集评估

[最终保留集评估报告](最终保留集评估报告.md)记录了锁定 T-Learner 逻辑回归、随机排序和 RFM 在相同覆盖比例下的独立比较。

| 结果 | 内容 |
|---|---|
| [锁定规则](metadata/evaluation_lock.json) | 在计算保留集指标前保存的模型、输入文件指纹、触达比例和采用门槛。 |
| [保留集特征](tables/holdout_features.csv) | 40,009 位客户的历史特征，沿用训练集确定的特征和分群口径。 |
| [保留集分数和排名](tables/holdout_scores.csv.gz) | 每位客户在三条策略下的分数与排名。第 1 至 12,002 名构成各自的触达名单。 |
| [前 30% 策略对照](tables/holdout_at30.csv) | 短信组和对照组样本量、购买人数、购买率差和置信区间。 |
| [候选与两条基线的配对比较](tables/holdout_candidate_vs_baselines.csv) | 领先幅度、考虑同一批客户的配对区间和名单重叠。 |
| [评估摘要](metadata/evaluation_summary.json) · [独立核验](metadata/verification.json) | 采用门槛的判定、验证集重放一致性和结果复算。 |
| [策略对照图](figures/holdout_uplift.png) | 三条策略的 Uplift@30% 和逐项区间。 |

运行命令位于 X5 项目根目录。模型评估使用与[第四阶段](../04_uplift_baselines/README.md)相同的 Python 依赖版本。重跑使用已保存的锁定文件。

```bash
python scripts/04_build_validation_features.py --split holdout
python scripts/05_holdout_evaluation.py
python scripts/plot_stage05.py
```

业务结论以锁定的配对比较为准。当前候选对随机排序的优势尚未得到独立确认。
