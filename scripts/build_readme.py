# -*- coding: utf-8 -*-
"""
根据 data.json + assets/_stats.json 生成 README.md。

折叠结构（用户指定）：
    <details open> 最近一个月（日柱图，默认展开）
    <details>      上一个月（日柱图）
    <details>      年（恰好本年时按周滚动，默认收起）

为什么正文没有颜色：
    实测 `gh api markdown` 的结果 —— <style> 被转义成可见文本，
    style="" / bgcolor / <font color> 全被剥掉，只剩 align / mark / kbd / details。
    所以所有色彩都必须由 SVG 承担；band.svg 是唯一能当"背景色"的近似手段。
"""
import json
import os
import sys

CN_MONTHS = "零一二三四五六七八九十"


def pic(base, alt, width=900):
    """浅色 / 深色双图。GitHub 会把它包进 <themed-picture>。"""
    return (
        '<picture>\n'
        '  <source media="(prefers-color-scheme: dark)" srcset="assets/%s-dark.svg">\n'
        '  <img src="assets/%s.svg" alt="%s" width="%d">\n'
        '</picture>' % (base, base, alt, width)
    )


def band(width=900):
    return (
        '<picture>\n'
        '  <source media="(prefers-color-scheme: dark)" srcset="assets/band-dark.svg">\n'
        '  <img src="assets/band.svg" alt="" width="%d" height="10">\n'
        '</picture>' % width
    )


def hours_block(hm):
    """「每天 · 按小时」那一层：全天累计 + 本月最忙的几天。"""
    if not hm:
        return ""
    per_hour = hm["per_hour"]
    peak = max(range(24), key=lambda h: per_hour[h])
    peak_n = per_hour[peak]

    parts = []
    # 全天累计
    parts.append(details(
        "<b>全天累计</b> · 峰值 %d 时（%d 次）· 共 %d 次" % (peak, peak_n, hm["total"]),
        pic("activity-hours-all", "按小时的提交分布（全天累计）"),
        open_=True,
    ))
    # 本月最忙的几天（默认收起，避免太长）
    for d in hm["top_days"][:5]:
        parts.append(details(
            "<b>%s</b> · %d 次" % (d["date"][5:], d["count"]),
            pic("activity-hours-%s" % d["date"], "%s 的逐小时提交分布" % d["date"]),
            open_=False,
        ))
    return "\n\n".join(parts)


def details(summary, body, open_=False):
    return '<details%s>\n<summary>%s</summary>\n\n%s\n\n</details>' % (
        " open" if open_ else "", summary, body)


def build(data, stats):
    login = data["login"]
    born = data["born"]
    today = data["generated_at"]

    hourly = stats.get("hourly")
    months = stats["months"][:]          # 旧 → 新
    newest = months[-1]
    older = months[:-1]

    total_all = stats["years"][-1]["total"] if stats["years"] else 0

    # ---- 年图（默认收起）----
    year_blocks = []
    for y in sorted({m["year"] for m in months}):
        rows = [r for r in stats["years"] if r["year"] == y]
        if not rows:
            continue
        info = rows[0]
        year_blocks.append(details(
            "<b>%d</b> · %d 周 · 合计 %d" % (y, info["weeks"], info["total"]),
            pic("activity-year-%d" % y, "%d 年按周活动柱状图" % y),
            open_=False,
        ))

    # ---- 月图 ----
    def month_block(m, open_):
        parts = m["parts"]
        summary = "<b>%d 月</b> · %d/%d 天有活动 · 合计 %d" % (
            m["month"], m["active"], m["days"], m["total"])
        return details(
            summary,
            pic("activity-%d-%02d" % (m["year"], m["month"]),
                "%d 年 %d 月逐日活动柱状图" % (m["year"], m["month"])),
            open_=open_,
        )

    # 最新月份展开时，"每天按小时"作为它的子层
    hours_inner = hours_block(hourly) if hourly else ""
    newest_block = details(
        "<b>%d 月</b> · %d/%d 天有活动 · 合计 %d" % (
            newest["month"], newest["active"], newest["days"], newest["total"]),
        pic("activity-%d-%02d" % (newest["year"], newest["month"]),
            "%d 年 %d 月逐日活动柱状图" % (newest["year"], newest["month"]))
        + ("\n\n" + details("<b>每天</b> · 按小时（%s）" % hourly["timezone"],
                            hours_inner, open_=True) if hours_inner else ""),
        open_=True,
    )
    older_blocks = "\n\n".join(month_block(m, False) for m in older)

    parts = newest["parts"]
    commit, pr, merged = parts[0], parts[1], parts[2]

    readme = """# 樱花祭 AI

`{login}` 是 [`yinghuajimew`](https://github.com/yinghuajimew) 的 AI 账号，
接手那些重复但必须做完的活：写改动、提 PR、合并、把想法先落成能跑的东西。

主力项目是 **[Nibnya](https://github.com/yinghuajimew/Nibnya)** —— 一个基于 Shizuku
的 Android Minecraft 基岩版 NBT 编辑器（Kotlin · AGPL-3.0 · 24 ★）。

{band}

## 活动

{pic_legend}

> 柱子的高度是当天活动次数，颜色区分类型：提交 {commit} 次 / 开 PR {pr} 次 / 合并 {merged} 次（本月）。
> 没有活动的日子不省略，只画一条 2px 的浅刻度——空着的日子也是记录。
>
> 小时图按 **北京时间** 分桶，数据来自逐条读取 commit 时间戳。GitHub 的贡献统计覆盖所有分支与仓库，
> 而 API 只能逐仓库逐分支扫，因此小时图的总数会少于日柱图（约八成），两者的**形状与峰值一致**。

{newest}

{older}

{year_blocks}

{band}

## 在做什么

| 项目 | 是什么 | 状态 |
|---|---|---|
| [Nibnya](https://github.com/yinghuajimew/Nibnya) | Android 基岩版 NBT 编辑器，Shizuku 直读 `/data`，不用 root 改存档 | Kotlin · 24 ★ |
| [elder-launcher](https://github.com/yinghuajimew/elder-launcher) | 长辈桌面 · Elder Launcher，极简桌面，大图标少层级，Android 6~10 | Kotlin · 1 ★ |
| [Juggler](https://github.com/juggler-ai/juggler) | AI 编码助手的可视化工作台，厂商中立 | JavaScript · 804 ★ |

{band}

## 说明

- 数据来自 GitHub 贡献统计，每天 UTC 00:20 自动重跑；本页生成于 {today}。
- 时间轴起点 {born}（本账号建号日）。更早的提交作者是 `yinghuajimew`，不计入。
- `yinghuajiai/Nibnya` 与 `yinghuajimew/Nibnya` 是同一份历史（OID 完全一致），只计一次。
- 账户合计 **{total_all}** 次活动。

"""

    return readme.format(
        login=login,
        born=born,
        today=today,
        total_all=total_all,
        band=band(),
        pic_legend=pic("legend", "图例：粉色提交、紫色开 PR、金色合并"),
        commit=commit,
        pr=pr,
        merged=merged,
        newest=newest_block,
        older=older_blocks,
        year_blocks="\n\n".join(year_blocks),
    )


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)

    with open(os.path.join(root, "data.json"), encoding="utf-8") as f:
        data = json.load(f)
    with open(os.path.join(root, "assets", "_stats.json"), encoding="utf-8") as f:
        stats = json.load(f)

    md = build(data, stats)
    path = os.path.join(root, "README.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)

    print("写出 README.md  %d 字符" % len(md))
    print("  月块: %d 个（最新默认展开）" % len(stats["months"]))
    print("  年块: %d 个（默认收起）" % len(stats["years"]))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
