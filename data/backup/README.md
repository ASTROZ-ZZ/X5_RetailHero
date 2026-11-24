# 原始数据完整备份

六张原始 CSV 使用无损 gzip 压缩并按顺序分成 7 卷。每卷不超过 90 MiB，所有卷均需下载。`manifest.json` 保存原始文件和每个分卷的字节数及 SHA-256。归档已通过逐文件还原读取校验。

在项目根目录执行以下命令，可校验分卷并还原到 `data/`。

```bash
python scripts/restore_source_data.py
```

还原程序只依赖 Python 标准库。若本地已有同名 CSV，程序会停止，避免覆盖。可指定另一个空目录。

```bash
python scripts/restore_source_data.py --output /path/to/empty_directory
```

数据来源及提供者原始说明见 [数据来源](../../docs/sources/README.md)。
