# 第六阶段 · 官方测试预测与项目总结

[X5 项目总结](X5项目总结.md)汇总数据处理、客户分析、短信实验与 Uplift 策略评价。官方测试预测使用全部有标签客户重训的 T-Learner 逻辑回归。

| 文件 | 内容 |
|---|---|
| [uplift_submission.csv](tables/uplift_submission.csv) | 交付文件，按官方提交样例的客户顺序排列，列为 `client_id,uplift`。 |
| [official_test_features.csv](tables/official_test_features.csv) | 官方测试客户的历史消费特征，采用训练阶段的特征定义和分析参考日。 |
| [官方测试特征摘要](metadata/official_test_features.json) | 特征覆盖、订单数、历史窗口与文件指纹。 |
| [预测摘要](metadata/submission_summary.json) | 重训客户数、预测范围、锁定配置和预测文件指纹。 |
| [独立核验结果](metadata/verification.json) | 客户覆盖、格式、顺序、分数范围与指纹的检查。 |

从 X5 项目根目录运行。重训使用[第四阶段](../04_uplift_baselines/README.md)的 Python 依赖版本。已生成官方测试特征时，可从第二条开始。

```bash
python scripts/06_build_test_features.py
python scripts/06_official_test_delivery.py
python scripts/verify_stage06.py
```

官方测试数据没有购买或处理标签。独立的策略评价仍以[最终保留集结果](../05_holdout_evaluation/最终保留集评估报告.md)为准。
