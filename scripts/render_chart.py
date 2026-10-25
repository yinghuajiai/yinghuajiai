# -*- coding: utf-8 -*-
"""
把 data.json 渲染成竖向堆叠柱 SVG。

已用 `gh api markdown` 实测过的 GitHub 渲染约束：
  · <style> 会被转义成可见文本；style="" / bgcolor / <font color> 全部被剥
    → 正文零样式，颜色只能来自图片
  · <picture> + prefers-color-scheme 有效（GitHub 会包一层 <themed-picture>）
  · <details> 可嵌套，open 保留
  · img 的 width 只吃像素值，百分比无效

输出到 assets/：
  activity-<yyyy-mm>.svg          当月逐日
  activity-year-<yyyy>.svg        当年按周（滚动）
  legend.svg                      图例
  band.svg                        纯色带（MD 里唯一能当"背景色"的东西）
  每个都有 -dark 版本
"""
import json
import os
import sys
from collections import defaultdict
from datetime import date, timedelta

# ---------- 色板：与方向 B 的纸感统一 ----------
PAPER = "#FFF9FB"          # 无卡片时的纸底
CARD = "#FFF0F6"           # 卡片底：淡樱粉（"简单颜色"的落点）
CARD_R = 10
INK_SOFT = "#7A5F6C"
FAINT = "#B49CA8"
RULE = "#EEDBE4"
GRID = "#F7EAF0"
GHOST = "#F4E2EA"
COLORS = {"commit": "#F4799C", "pr": "#8B7AA8", "merge": "#E2B24E"}

D_PAPER = "#17111A"
D_CARD = "#1E151D"
D_INK_SOFT = "#C2A5B4"
D_FAINT = "#8A6E7C"
D_RULE = "#33222C"
D_GRID = "#241A22"
D_GHOST = "#2A1E26"
D_COLORS = {"commit": "#F4799C", "pr": "#9C8BB8", "merge": "#E2B24E"}

FONT = "'Microsoft YaHei','PingFang SC','Noto Sans SC','Segoe UI',sans-serif"
LABEL = {"commit": "提交", "pr": "开 PR", "merge": "合并"}
ORDER = ["commit", "pr", "merge"]


class Pal:
    def __init__(self, dark=False):
        self.dark = dark
        self.paper = D_PAPER if dark else PAPER
        self.card = D_CARD if dark else CARD
        self.soft = D_INK_SOFT if dark else INK_SOFT
        self.faint = D_FAINT if dark else FAINT
        self.rule = D_RULE if dark else RULE
        self.grid = D_GRID if dark else GRID
        self.ghost = D_GHOST if dark else GHOST
        self.colors = D_COLORS if dark else COLORS


def nice_max(v):
    if v <= 4:
        return 4
    for s in (5, 8, 10, 15, 20, 25, 30, 40, 50, 60, 80, 100):
        if v <= s:
            return s
    return ((v + 49) // 50) * 50


def bars(rows, width, height, pal, *, show_y=True, show_values=True,
         label_every=1, pad_left=40, pad_bottom=26, card=False, radius=0):
    """rows: [(date, {kind: n}, total)]"""
    L, R, T, B = pad_left, 8, 26, pad_bottom
    pw, ph = width - L - R, height - T - B
    slot = pw / len(rows)
    bw = max(3.0, min(slot * 0.62, 22))
    top = nice_max(max(1, max(t for _, _, t in rows)))

    def y(v):
        return T + ph - (v / top) * ph

    p = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" role="img">'
         % (width, height, width, height),
         '<rect width="%d" height="%d" fill="%s"%s/>'
         % (width, height, pal.card if card else pal.paper,
            (' rx="%d"' % radius) if radius else '')]

    for i in range(5):
        val = top * i / 4
        yy = y(val)
        dash = '' if i == 0 else ' stroke-dasharray="1 4"'
        p.append('<line x1="%d" y1="%.2f" x2="%d" y2="%.2f" stroke="%s" stroke-width="1"%s/>'
                 % (L, yy, width - R, yy, pal.rule if i == 0 else pal.grid, dash))
        if show_y:
            p.append('<text x="%d" y="%.2f" font-size="10" fill="%s" text-anchor="end" '
                     'font-family="%s">%d</text>' % (L - 9, yy + 3.6, pal.faint, FONT, round(val)))

    # 月份分隔（跨月才有意义）
    last = None
    for i, (d, seg, tot) in enumerate(rows):
        key = (d.year, d.month)
        if key == last:
            continue
        last = key
        x = L + i * slot
        if i:
            p.append('<line x1="%.2f" y1="%d" x2="%.2f" y2="%d" stroke="%s" stroke-width="1"/>'
                     % (x, T - 8, x, T + ph, pal.rule))
        p.append('<text x="%.2f" y="%d" font-size="11.5" fill="%s" font-family="%s">%d 月</text>'
                 % (x + (0 if i == 0 else 6), T - 12, pal.soft, FONT, d.month))

    for i, (d, seg, tot) in enumerate(rows):
        x = L + i * slot + (slot - bw) / 2
        base = T + ph
        if tot == 0:
            p.append('<rect x="%.2f" y="%.2f" width="%.2f" height="2" fill="%s" rx="1"/>'
                     % (x, base - 2, bw, pal.ghost))
            continue
        acc = 0.0
        for kind in ORDER:
            v = seg.get(kind, 0)
            if not v:
                continue
            h = (v / top) * ph
            p.append('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" fill="%s"/>'
                     % (x, base - acc - h, bw, max(h, 1.2), pal.colors[kind]))
            acc += h
        if show_values:
            p.append('<text x="%.2f" y="%.2f" font-size="9.5" fill="%s" text-anchor="middle" '
                     'font-family="%s">%d</text>'
                     % (x + bw / 2, base - acc - 5, pal.faint, FONT, tot))

    for i, (d, seg, tot) in enumerate(rows):
        if i % label_every:
            continue
        p.append('<text x="%.2f" y="%d" font-size="9.5" fill="%s" text-anchor="middle" '
                 'font-family="%s">%d/%d</text>'
                 % (L + i * slot + slot / 2, T + ph + 16, pal.faint, FONT, d.month, d.day))

    p.append("</svg>")
    return "\n".join(p)


def legend(width, pal):
    h = 22
    p = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">'
         % (width, h, width, h),
         '<rect width="%d" height="%d" fill="%s"/>' % (width, h, pal.paper)]
    x = 1
    for kind in ORDER:
        p.append('<rect x="%d" y="6" width="9" height="9" rx="2" fill="%s"/>' % (x, pal.colors[kind]))
        p.append('<text x="%d" y="14.5" font-size="11.5" fill="%s" font-family="%s">%s</text>'
                 % (x + 14, pal.faint, FONT, LABEL[kind]))
        x += 26 + len(LABEL[kind]) * 12
    p.append("</svg>")
    return "\n".join(p)


def band(width, height, pal, card=False):
    """纯色带：README 里唯一能实现"背景色"的手段。"""
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">'
            '<rect width="%d" height="%d" fill="%s"/></svg>'
            % (width, height, width, height, width, height,
               pal.card if card else pal.paper))


# ---------------------------------------------------------------- 数据整形
def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_day_map(raw):
    day = defaultdict(lambda: {"commit": 0, "pr": 0, "merge": 0})
    for d, repos in raw["day_repo"].items():
        for n in repos.values():
            day[d]["commit"] += n
    for p in raw["prs"]:
        c = p["createdAt"][:10]
        day[c]["pr"] += 1
        if p.get("mergedAt"):
            day[p["mergedAt"][:10]]["merge"] += 1
    return day


def month_rows(day, y, m, today):
    start = date(y, m, 1)
    end = min(today, date(y + (m == 12), (m % 12) + 1, 1) - timedelta(days=1))
    rows = []
    d = start
    while d <= end:
        seg = {k: v for k, v in day.get(d.isoformat(), {}).items() if v}
        rows.append((d, seg, sum(seg.values())))
        d += timedelta(days=1)
    return rows


def year_rows(day, y, born, today):
    rows = []
    d = max(born, date(y, 1, 1))
    end = min(today, date(y, 12, 31))
    while d <= end:
        stop = min(d + timedelta(days=6), end)
        seg = defaultdict(int)
        dd = d
        while dd <= stop:
            for k, v in day.get(dd.isoformat(), {}).items():
                seg[k] += v
            dd += timedelta(days=1)
        rows.append((d, {k: v for k, v in seg.items() if v}, sum(seg.values())))
        d = stop + timedelta(days=1)
    return rows


def month_stat(rows):
    tot = [sum(r[1].get(k, 0) for r in rows) for k in ORDER]
    return tot, sum(tot), sum(1 for r in rows if r[2]), len(rows)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    out_dir = os.path.join(root, "assets")
    os.makedirs(out_dir, exist_ok=True)

    raw = load(os.path.join(root, "data.json"))
    day = build_day_map(raw)
    born = date.fromisoformat(raw["born"])
    today = date.fromisoformat(raw["generated_at"])

    written = []

    def emit(name, svg):
        with open(os.path.join(out_dir, name), "w", encoding="utf-8") as f:
            f.write(svg)
        written.append(name)

    # 最近两个月（当月 + 上月）
    months = []
    cur = date(today.year, today.month, 1)
    for _ in range(2):
        months.append((cur.year, cur.month))
        prev = cur - timedelta(days=1)
        cur = date(prev.year, prev.month, 1)
    months.reverse()  # 旧 → 新

    stats = {}
    for y, m in months:
        rows = month_rows(day, y, m, today)
        tot, total, active, ndays = month_stat(rows)
        stats[(y, m)] = dict(total=total, active=active, days=ndays, parts=tot)
        for dark in (False, True):
            emit("activity-%d-%02d%s.svg" % (y, m, "-dark" if dark else ""),
                 bars(rows, 900, 210, Pal(dark), label_every=2, pad_left=44,
                      card=True, radius=12))

    # 年度（按周滚动）
    year_stats = {}
    for y in sorted({today.year} | {m[0] for m in months}):
        rows = year_rows(day, y, born, today)
        tot = [sum(r[1].get(k, 0) for r in rows) for k in ORDER]
        year_stats[y] = dict(total=sum(tot), weeks=len(rows))
        for dark in (False, True):
            emit("activity-year-%d%s.svg" % (y, "-dark" if dark else ""),
                 bars(rows, 900, 158, Pal(dark), show_y=False, show_values=False,
                      label_every=1, pad_left=16, pad_bottom=22,
                      card=True, radius=12))

    for dark in (False, True):
        tail = "-dark" if dark else ""
        emit("legend%s.svg" % tail, legend(900, Pal(dark)))
        emit("band%s.svg" % tail, band(900, 10, Pal(dark)))
        emit("band-card%s.svg" % tail, band(900, 10, Pal(dark), card=True))

    # 统计写回，供 README 生成使用
    meta_path = os.path.join(root, "assets", "_stats.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({
            "months": [{"year": y, "month": m, **stats[(y, m)]} for y, m in months],
            "years": [{"year": y, **v} for y, v in sorted(year_stats.items())],
        }, f, ensure_ascii=False, indent=1)

    print("生成 %d 个 SVG" % len(written))
    for y, m in months:
        s = stats[(y, m)]
        print("  %d-%02d 合计 %d · %d/%d 天有活动" % (y, m, s["total"], s["active"], s["days"]))
    for y, s in sorted(year_stats.items()):
        print("  %d 全年 %d 次 · %d 周" % (y, s["total"], s["weeks"]))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
