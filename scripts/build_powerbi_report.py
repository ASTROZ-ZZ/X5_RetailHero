#!/usr/bin/env python3
"""Build the portable PBIP from existing, non-identifying aggregate results."""

import argparse
from collections import OrderedDict
import csv
import json
from pathlib import Path
import subprocess
from uuid import NAMESPACE_URL, uuid5
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
NAME = "X5RetailHero"
VIOLET, GOLD, INK, PAPER = "#5A36A3", "#ECCA52", "#24163D", "#F6F3FB"
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item"
LABELS = {"t_logistic": "T-Learner", "random": "随机排序", "rfm": "RFM 规则",
          "s_logistic": "S-Learner", "t_hist_gradient": "T-Learner 梯度提升树",
          "purchase_probability": "普通购买概率", "base_t": "原 T-Learner",
          "behavior_t": "增强 T-Learner", "interaction_s": "带交互项 S-Learner"}


def rows(stage, file):
    with (RESULTS / stage / "tables" / (file + ".csv")).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def metadata(stage, file):
    return json.loads((RESULTS / stage / "metadata" / (file + ".json")).read_text())


def collect():
    audit = metadata("01_data_audit", "audit_summary")
    segments = rows("02_customer_analysis", "segment_summary")
    cohort = [r for r in rows("02_customer_analysis", "cohort_repeat")
              if r["status"] == "complete" and int(r["month_offset"]) > 0]
    effects = rows("03_sms_experiment", "purchase_rate_effects")
    val = rows("04_uplift_baselines", "validation_at30")
    hold = rows("05_holdout_evaluation", "holdout_at30")
    paired = {
        "验证集": rows("04_uplift_baselines", "candidate_vs_baselines"),
        "独立保留集": rows("05_holdout_evaluation", "holdout_candidate_vs_baselines"),
    }
    overall = effects[0]
    high = [r for r in segments if r["segment"].startswith("高价值")]
    raw = {f["table"]: f["rows"] for f in audit["files"]}
    curves = [r for r in rows("04_uplift_baselines", "validation_curves")
              if r["policy"] in ("random", "t_logistic", "rfm")]
    optimization = rows("07_uplift_optimization", "model_summary")
    overview = [[raw["purchases"], raw["clients"], raw["uplift_train"],
                 raw["uplift_test"], float(overall["difference_pp"]),
                 float(paired["独立保留集"][0]["difference_pp"]),
                 sum(float(r["customer_share"]) for r in high),
                 sum(float(r["sales_share"]) for r in high)]]
    strategy_fields = {"Policy": "s", "Uplift": "n", "Lower": "n", "Upper": "n"}
    return OrderedDict({
        "Overview": ({"Lines": "i", "Clients": "i", "Labeled": "i", "Scored": "i",
                      "ATE": "n", "Gap": "n", "HighClients": "p", "HighSpend": "p"}, overview),
        "Segments": ({"Segment": "s", "Clients": "i", "Orders": "i", "Spend": "n",
                      "ClientShare": "p", "SpendShare": "p", "GapDays": "n",
                      "OrderValue": "n"},
                     [[r["segment"], int(r["customers"]), int(r["orders"]),
                       *[float(r[k]) for k in ("sales", "customer_share", "sales_share",
                                               "median_customer_gap_days", "order_weighted_aov")]]
                      for r in segments]),
        "Cohort": ({"Cohort": "s", "Month": "s", "Offset": "i", "Repeat": "p", "Population": "i"},
                   [[r["cohort_month"], r["activity_month"], int(r["month_offset"]),
                     float(r["repeat_rate"]), int(r["cohort_customers"])] for r in cohort]),
        "Experiment": ({"Segment": "s", "ControlN": "i", "SmsN": "i", "Control": "p", "SMS": "p",
                        "Effect": "n", "Lower": "n", "Upper": "n", "HolmP": "f"},
                       [[r["segment"], int(r["control_n"]), int(r["sms_n"]),
                         *[float(r[k]) for k in ("control_rate", "sms_rate", "difference_pp",
                                                 "ci_low_pp", "ci_high_pp")],
                         float(r["holm_p"]) if r["holm_p"] else None] for r in effects]),
        "HoldoutOverview": (strategy_fields, [[LABELS[r["policy"]],
                            *[float(r[k]) for k in ("uplift_pp", "ci_low_pp", "ci_high_pp")]]
                            for r in hold]),
        "Policies": ({"Sample": "s", "Policy": "s", "Uplift": "n", "Lower": "n", "Upper": "n",
                      "AUUC": "n", "Qini": "q", "Selected": "i"},
                     [[sample, LABELS[r["policy"]],
                       *[float(r[k]) for k in ("uplift_pp", "ci_low_pp", "ci_high_pp")],
                       float(r["auuc"]) if r.get("auuc") else None,
                       float(r["qini"]) if r.get("qini") else None, int(r["selected"])]
                      for sample, table in (("验证集", val), ("独立保留集", hold)) for r in table]),
        "Comparisons": ({"Sample": "s", "Comparator": "s", "Effect": "n", "Lower": "n", "Upper": "n"},
                        [[sample, LABELS[r["comparator"]],
                          *[float(r[k]) for k in ("difference_pp", "ci_low_pp", "ci_high_pp")]]
                         for sample, table in paired.items() for r in table]),
        "Curves": ({"Reach": "p", "Policy": "s", "Uplift": "n"},
                   [[int(r["reach_pct"]) / 100, LABELS[r["policy"]], float(r["uplift_pp"])]
                    for r in curves]),
        "Optimization": ({"Model": "s", "VsRandom": "n", "VsBase": "n", "Positive": "i"},
                         [[LABELS[r["model"]], float(r["mean_vs_random_pp"]),
                           float(r["mean_vs_base_t_pp"]), int(r["folds_positive_vs_base_t"])]
                          for r in optimization]),
    })


def dump(file, obj):
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def literal(value):
    if isinstance(value, str):
        value = "'" + value.replace("'", "''") + "'"
    elif isinstance(value, bool):
        value = str(value).lower()
    elif isinstance(value, int):
        value = f"{value}L"
    return {"expr": {"Literal": {"Value": value}}}


def color(value):
    return {"solid": {"color": literal(value)}}


def obj(**props):
    return [{"properties": props}]


def field(entity, name, label, kind="Column"):
    return {"field": {kind: {"Expression": {"SourceRef": {"Entity": entity}}, "Property": name}},
            "queryRef": f"{entity}.{name}", "nativeQueryRef": label, "active": True}


def column(entity, name, label):
    return field(entity, name, label)


def measure(entity, name, label):
    return field(entity, "m" + name, label, "Measure")


class Page:
    def __init__(self, definition, slug, name, subtitle):
        self.id = uuid5(NAMESPACE_URL, "x5/page/" + slug).hex[:20]
        self.path = definition / "pages" / self.id
        self.count = 0
        dump(self.path / "page.json", {
            "$schema": f"{SCHEMA}/report/definition/page/2.1.0/schema.json",
            "name": self.id, "displayName": name, "displayOption": "FitToPage",
            "height": 720, "width": 1280,
            "objects": {"background": obj(color=color(PAPER), transparency=literal(0))},
        })
        self.note(32, 14, 1216, 54, name, size=23, background=INK, foreground="#FFFFFF")
        self.note(32, 70, 1216, 42, subtitle, size=15)

    def visual(self, typ, pos, title="", roles=None, objects=None, order=None, container=None):
        self.count += 1
        name = uuid5(NAMESPACE_URL, f"x5/{self.id}/{self.count}").hex[:20]
        vis = {"visualType": typ, "drillFilterOtherVisuals": True}
        if roles:
            vis["query"] = {"queryState": {k: {"projections": v} for k, v in roles.items()}}
            if order:
                vis["query"]["sortDefinition"] = {
                    "sort": [{"field": order[0]["field"], "direction": order[1]}],
                    "isDefaultSort": False,
                }
        if objects:
            vis["objects"] = objects
        container_objects = {
            "background": obj(show=literal(True), color=color("#FFFFFF"), transparency=literal(0))
        }
        if title:
            container_objects["title"] = obj(
                show=literal(True), text=literal(title), fontColor=color(INK),
                fontFamily=literal("SimHei"), fontSize=literal(14), alignment=literal("left")
            )
        if container:
            container_objects.update(container)
        vis["visualContainerObjects"] = container_objects
        x, y, width, height = pos
        assert 0 <= x < x + width <= 1280 and 0 <= y < y + height <= 720
        dump(self.path / "visuals" / name / "visual.json", {
            "$schema": f"{SCHEMA}/report/definition/visualContainer/2.9.0/schema.json",
            "name": name, "position": {"x": x, "y": y, "width": width, "height": height,
                                       "z": self.count, "tabOrder": self.count},
            "visual": vis,
        })

    def note(self, x, y, width, height, msg, size=14, background=PAPER, foreground=INK):
        paragraphs = [{"textRuns": [{"value": line,
                       "textStyle": {"fontFamily": "SimHei", "fontSize": f"{size}pt",
                                     "color": foreground}}]} for line in msg.split("\n")]
        self.visual("textbox", (x, y, width, height),
                    objects={"general": obj(paragraphs=paragraphs)},
                    container={"background": obj(show=literal(True), color=color(background),
                                                 transparency=literal(0))})

    def card(self, x, y, width, title, name, height=119):
        self.visual("card", (x, y, width, height), title,
                    {"Values": [measure("Overview", name, title)]},
                    {"categoryLabels": obj(show=literal(False)),
                     "labels": obj(color=color(VIOLET), fontFamily=literal("Times New Roman"),
                                   fontSize=literal(32), labelDisplayUnits=literal(1))})

    def table(self, pos, title, *fields):
        self.visual("tableEx", pos, title, {"Values": list(fields)},
                    {"total": obj(totals=literal(False))})

    def bars(self, pos, title, category, *values):
        self.visual("clusteredBarChart", pos, title, {"Category": [category], "Y": list(values)},
                    order=(values[-1], "Descending"))

    def slicer(self, pos, title, entity, name):
        self.visual("slicer", pos, "", {"Values": [column(entity, name, title)]},
                    {"data": obj(mode=literal("HorizontalList")),
                     "header": obj(text=literal(title), show=literal(True))})


def build_pages(definition):
    c, m = column, measure
    pages = []
    page = Page(definition, "executive", "01  决策总览",
                "X5 RetailHero   /   零售营销与增量决策  ·  金黄色标记重点，个百分点统一以 pp 表示")
    pages.append(page)
    for i, (name, title) in enumerate([("Lines", "商品交易明细"), ("Clients", "历史客户"),
                                        ("ATE", "短信整体购买率差（pp）"),
                                        ("Gap", "保留集模型对随机（pp）")]):
        page.card(32 + i * 307, 116, 295, title, name)
    page.bars((32, 250, 590, 370), "客户占比与历史消费额占比",
              c("Segments", "Segment", "客群"), m("Segments", "ClientShare", "客户占比"),
              m("Segments", "SpendShare", "消费额占比"))
    page.table((638, 250, 610, 244), "独立保留集 · 仅触达 30% 时的策略比较",
               c("HoldoutOverview", "Policy", "排序策略"), m("HoldoutOverview", "Uplift", "购买率差（pp）"),
               m("HoldoutOverview", "Lower", "区间下限"), m("HoldoutOverview", "Upper", "区间上限"))
    page.note(638, 510, 610, 110, "历史短信活动有正向购买率差。\n模型相对随机的区间跨零，按既定门槛保留候选。\n下一步采用同预算随机试点。", 16, "#F9EDB5")
    page.note(32, 647, 1216, 40, "数据来自 X5 RetailHero 公开数据集及项目既有汇总结果。购买率差不可直接换算成利润。")

    page = Page(definition, "customers", "02  客户行为",
                "固定训练集 120,022 客户   /   使用客群切片器查看消费结构、复购间隔及客单价")
    pages.append(page)
    page.slicer((32, 117, 1216, 86), "RFM 客群", "Segments", "Segment")
    page.bars((32, 218, 685, 298), "按客群比较客户占比与消费额占比",
              c("Segments", "Segment", "客群"), m("Segments", "ClientShare", "客户占比"),
              m("Segments", "SpendShare", "消费额占比"))
    page.table((732, 218, 516, 298), "完整月份的同群复购",
               c("Cohort", "Cohort", "同群月份"), c("Cohort", "Month", "复购月份"),
               m("Cohort", "Repeat", "复购率"), m("Cohort", "Population", "同群客户"))
    page.table((32, 531, 1216, 141), "消费指标 · 随客群筛选",
               c("Segments", "Segment", "客群"), m("Segments", "Clients", "客户数"),
               m("Segments", "Orders", "订单量"), m("Segments", "OrderValue", "订单加权客单价"),
               m("Segments", "GapDays", "客户复购间隔中位数（天）"))

    page = Page(definition, "experiment", "03  短信活动",
                "训练集实验组与对照组比较   /   95% 置信区间；Holm 校正覆盖五个客群")
    pages.append(page)
    page.slicer((32, 117, 1216, 86), "分析客群", "Experiment", "Segment")
    page.bars((32, 218, 654, 398), "短信组与对照组的购买率",
              c("Experiment", "Segment", "客群"), m("Experiment", "Control", "对照组购买率"),
              m("Experiment", "SMS", "短信组购买率"))
    page.table((702, 218, 546, 398), "客群购买率差及 95% 置信区间",
               c("Experiment", "Segment", "客群"), m("Experiment", "Effect", "差值（pp）"),
               m("Experiment", "Lower", "区间下限"), m("Experiment", "Upper", "区间上限"),
               m("Experiment", "HolmP", "Holm p"))
    page.note(32, 634, 1216, 46, "各客群组内效果用于生成假设；高价值活跃与待唤醒的直接差异区间跨零。")

    page = Page(definition, "strategy", "04  排序验证",
                "训练、验证、独立保留分工固定   /   点击样本切片器，切换策略评估；曲线始终显示验证集")
    pages.append(page)
    page.slicer((32, 117, 1216, 80), "评估样本", "Samples", "Sample")
    reach = c("Curves", "Reach", "触达比例")
    page.visual("lineChart", (32, 212, 631, 356), "验证集 · 覆盖人群内的购买率差",
                {"Category": [reach], "Y": [m("Curves", "Uplift", "购买率差（pp）")],
                 "Series": [c("Curves", "Policy", "排序策略")]}, order=(reach, "Ascending"))
    page.table((680, 212, 568, 207), "触达 30% · 各策略估计",
               c("Policies", "Sample", "样本"), c("Policies", "Policy", "策略"),
               m("Policies", "Uplift", "差值（pp）"), m("Policies", "AUUC", "AUUC"),
               m("Policies", "Qini", "Qini"))
    page.table((680, 433, 568, 238), "配对比较 · 模型相对基准（pp）",
               c("Comparisons", "Sample", "样本"), c("Comparisons", "Comparator", "基准"),
               m("Comparisons", "Effect", "差值"), m("Comparisons", "Lower", "95% CI 下限"),
               m("Comparisons", "Upper", "95% CI 上限"))
    page.table((32, 581, 631, 90), "重复交叉验证 · 相对原模型（pp）",
               c("Optimization", "Model", "模型"), m("Optimization", "VsBase", "平均差值"),
               m("Optimization", "Positive", "胜出折数 / 15"))
    return pages


FORMATS = {"i": "#,0", "n": "0.00", "f": "0.00E+00", "p": "0.0%", "q": "0.000"}
M_TYPES = {"s": "text", "i": "Int64.Type", "n": "number", "f": "number", "p": "number", "q": "number"}
T_TYPES = {"s": "string", "i": "int64", "n": "double", "f": "double", "p": "double", "q": "double"}


def m_literal(value):
    if value is None:
        return "null"
    if isinstance(value, str):
        return '"' + value.replace('"', '""') + '"'
    return repr(value)


def build_model(folder, data):
    definition = folder / "definition"
    (definition / "tables").mkdir(parents=True)
    data["Samples"] = ({"Sample": "s"}, [["验证集"], ["独立保留集"]])
    dump(folder / "definition.pbism", {
        "$schema": f"{SCHEMA}/semanticModel/definitionProperties/1.0.0/schema.json",
        "version": "4.0", "settings": {},
    })
    dump(folder / ".platform", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "SemanticModel", "displayName": NAME},
        "config": {"version": "2.0", "logicalId": str(uuid5(NAMESPACE_URL, "x5/model"))},
    })
    (definition / "database.tmdl").write_text("database\n\tcompatibilityLevel: 1600\n")
    (definition / "model.tmdl").write_text(
        "model Model\n\tculture: zh-CN\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n"
        "\tsourceQueryCulture: zh-CN\n\tdataAccessOptions\n\t\tlegacyRedirects\n"
        "\t\treturnErrorValuesAsNull\n\n"
        + "\n".join("ref table " + k for k in data) + "\n")
    (definition / "relationships.tmdl").write_text("\n".join(
        f"relationship {uuid5(NAMESPACE_URL, 'x5/sample/' + name)}\n"
        f"\tfromColumn: {name}.Sample\n\ttoColumn: Samples.Sample\n"
        for name in ("Policies", "Comparisons")) + "\n")
    for name, (columns, records) in data.items():
        buf = [f"table {name}", ""]
        for k, dtype in columns.items():
            if dtype != "s":
                agg = "SUM" if k in ("Clients", "Orders", "Spend") else "SELECTEDVALUE"
                buf.extend([f"\tmeasure m{k} = {agg}({name}[{k}])",
                            f"\t\tformatString: {FORMATS[dtype]}", ""])
            buf.extend([f"\tcolumn {k}", f"\t\tdataType: {T_TYPES[dtype]}",
                        f"\t\tsourceColumn: {k}", "\t\tsummarizeBy: none"])
            if dtype != "s":
                buf.append(f"\t\tformatString: {FORMATS[dtype]}")
            buf.append("")
        types = ", ".join(f"{k} = {M_TYPES[dtype]}" for k, dtype in columns.items())
        buf += [f"\tpartition {name} = m", "\t\tmode: import", "\t\tsource =",
                "\t\t\t\tlet",
                f"\t\t\t\t\tSource = #table(type table [{types}], {{"]
        m_rows = ["{" + ", ".join(map(m_literal, r)) + "}" for r in records]
        buf += ["\t\t\t\t\t\t" + line for line in ",\n".join(m_rows).splitlines()]
        buf += ["\t\t\t\t\t})", "\t\t\t\tin", "\t\t\t\t\tSource", ""]
        (definition / "tables" / f"{name}.tmdl").write_text("\n".join(buf), encoding="utf-8")


def build_report(folder, cli):
    subprocess.run([cli, "scaffold", str(folder), "--offline", "--name", NAME,
                    "--model-path", f"../{NAME}.SemanticModel"], check=True)
    report = folder / f"{NAME}.Report"
    definition = report / "definition"
    pmeta = definition / "pages" / "pages.json"
    info = json.loads(pmeta.read_text())
    placeholder = pmeta.parent / info["activePageName"]
    (placeholder / "page.json").unlink()
    placeholder.rmdir()
    pages = build_pages(definition)
    info.update(pageOrder=[p.id for p in pages], activePageName=pages[0].id)
    dump(pmeta, info)
    # Apply a report-wide palette through Power BI's registered custom theme.
    theme_file = "X5PurpleGold.json"
    theme = {"name": theme_file, "dataColors": [VIOLET, GOLD, "#9D80D1", "#604779"],
             "background": PAPER, "foreground": INK, "tableAccent": VIOLET,
             "textClasses": {
                 "callout": {"fontFace": "Times New Roman"},
                 "title": {"fontFace": "SimHei"},
                 "header": {"fontFace": "SimHei"},
                 "label": {"fontFace": "SimSun"},
             }}
    dump(report / "StaticResources" / "RegisteredResources" / theme_file, theme)
    report_file = definition / "report.json"
    info = json.loads(report_file.read_text())
    info["themeCollection"]["customTheme"] = {
        "name": theme_file, "type": "RegisteredResources",
        "reportVersionAtImport": info["themeCollection"]["baseTheme"]["reportVersionAtImport"],
    }
    info["resourcePackages"].append({"name": "RegisteredResources", "type": "RegisteredResources",
                                     "items": [{"name": theme_file, "path": theme_file,
                                                "type": "CustomTheme"}]})
    dump(report_file, info)


def package(folder, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(folder.rglob("*")):
            if file.is_file():
                archive.write(file, Path(NAME) / file.relative_to(folder))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", required=True)
    parser.add_argument("--folder", type=Path, required=True)
    parser.add_argument("--zip", type=Path)
    args = parser.parse_args()
    build_report(args.folder, args.cli)
    build_model(args.folder / f"{NAME}.SemanticModel", collect())
    (args.folder / "打开说明.txt").write_text(
        "X5 RetailHero | Power BI Desktop 项目\n\n"
        "1. 完整解压 ZIP，保持 .pbip 和两个子目录相邻。\n"
        "2. 在 Windows 最新版 Power BI Desktop 中打开 X5RetailHero.pbip。"
        "如需启用 PBIP 或 PBIR，在「文件 → 选项和设置 → 选项 → 预览功能」中启用，重启。\n"
        "3. 若模型数据缓存尚未建立，选择「主页 → 刷新」。汇总数据内嵌于模型，无需连接外部数据库或修改路径。\n"
        "4. 报表含决策总览、客户行为、短信活动、排序验证四页。"
        "切片器作用范围见对应页的副标题。可在 Windows 打开或发布后另存工作副本。\n"
        "构建机为 macOS，验证范围为项目文件及数据绑定；原生渲染与刷新待在 Desktop 验证。\n"
        "项目仅包含汇总结果。源数据和方法参见企业报告的溯源页。\n",
        encoding="utf-8")
    subprocess.run([args.cli, "validate", str(args.folder / f"{NAME}.pbip"), "--no-schema",
                    "--format", "text"], check=True)
    if args.zip:
        package(args.folder, args.zip)


if __name__ == "__main__":
    main()
