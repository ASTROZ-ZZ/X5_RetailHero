> 当前文件状态（2026-11-12）：项目数据已统一转换为 `../../data/` 中的 CSV，校验通过后已删除原压缩文件或 Parquet 文件。下方下载说明及清单保留历史下载状态，文件名、大小和校验值描述的是转换前原件。当前读取路径请使用项目 `data/` 下的 `.csv` 文件。

# X5 RetailHero 数据

已下载完整版 6 张表，位于 `raw/`，合计约 623 MB。文件保持 CSV.gz 压缩格式，Pandas 可以直接读取，无需先解压。

| 文件 | 内容 |
| --- | --- |
| `clients.csv.gz` | 客户基本信息、年龄、性别、首次发卡和兑换时间 |
| `products.csv.gz` | 商品信息、分类、品牌和供应商 |
| `purchases.csv.gz` | 营销触达前的购买明细 |
| `uplift_train.csv.gz` | 营销实验训练数据，含处理组标志与购买结果 |
| `uplift_test.csv.gz` | 竞赛测试客户列表 |
| `uplift_sample_submission.csv.gz` | 预测提交样例 |

## 来源与校验

- 官方说明：https://ods.ai/competitions/x5-retailhero-uplift-modeling/data
- 本次实际下载的公开镜像：https://huggingface.co/datasets/pytorch-lifestream/retailhero-uplift
- 原始官方 ZIP：https://storage.yandexcloud.net/datasouls-ods/materials/9c6913e5/retailhero-uplift.zip
- 本次交付为上述镜像的 6 份压缩数据文件，未下载完整官方 ZIP。
- 每个文件均已核验字节数和镜像 Git LFS 的 SHA-256；版本、下载地址和校验值见 `download_manifest.json`。
- `verification_report.json` 记录了本地再次校验结果及实际读取的字段名。
- `SOURCE_README.md` 保留镜像提供者的数据说明。

## 读取示例

在当前 Data_Analysis 目录下运行：

```python
import pandas as pd

clients = pd.read_csv('X5_RetailHero/raw/clients.csv.gz', dtype={'client_id': str})
train = pd.read_csv('X5_RetailHero/raw/uplift_train.csv.gz', dtype={'client_id': str})
for purchases in pd.read_csv('X5_RetailHero/raw/purchases.csv.gz', chunksize=500_000):
    # 按批处理购买记录，避免一次占用大量内存。
    print(purchases.shape)
    break
```

## 命令行重新下载

在上一级目录运行 `bash download_datasets.command`。该脚本并行下载、支持断点续传和重试，并跳过已经通过校验的文件。运行 `bash download_datasets.command --official` 可另外下载并解压两个项目的官方原始 ZIP；官方服务器可能较慢。
