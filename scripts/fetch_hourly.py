# -*- coding: utf-8 -*-
"""
采集「按小时」的提交分布，按北京时间（UTC+8）分桶。

为什么要单独写一个采集器：
    contributionsCollection 只给「某仓库某天几次」，拿不到小时。
    要小时就必须读每个 commit 的 committedDate，而这只能逐仓库、逐分支扫。

口径说明（写进 README 图注）：
    GitHub 的贡献统计包含所有分支、所有仓库；API 只能逐个扫，扫不全。
    所以小时图的总数会略少于日柱图（日柱图用 contributionsCollection 的口径）。
    实测差距约 15~20%，已在图注中注明。

输出 hourly.json：
    {
      "timezone": "Asia/Shanghai (UTC+8)",
      "days": { "2026-10-22": [0,0,...,n,...],   # 24 个元素，下标=小时
                ... },
      "total": 153,
      "source_repos": [...]
    }
"""
import json
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

TZ_OFFSET = 8  # 北京时间


def gh(*args, timeout=120):
    p = subprocess.run(
        ["gh", *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**os.environ, "NO_COLOR": "1", "GH_NO_UPDATE_NOTIFIER": "1"},
        timeout=timeout,
    )
    if p.returncode != 0:
        raise RuntimeError("gh %s: %s" % (" ".join(args[:2]), (p.stderr or "").strip()[:200]))
    return p.stdout.strip()


def list_repos(login):
    """
    要扫哪些仓库？不能只看「账号名下的仓库」：
      · 主力提交在 yinghuajimew/Nibnya（fork 自别的账号）
      · 还有 juggler-ai/juggler（组织仓库）
    正确来源是贡献统计自己列出的仓库清单。
    """
    # from 不能太早：contributionsCollection 的窗口上限是一年，传 2008 会返回空数组。
    # 用账号建号日作为起点。
    created = json.loads(gh("api", "users/%s" % login))["created_at"]
    q = """
    query {
      user(login: "%s") {
        contributionsCollection(from: "%s") {
          commitContributionsByRepository(maxRepositories: 100) {
            repository { nameWithOwner }
          }
        }
      }
    }""" % (login, created)
    data = json.loads(gh("api", "graphql", "-f", "query=" + q))
    repos = data["data"]["user"]["contributionsCollection"]["commitContributionsByRepository"]
    out = []
    for r in repos:
        owner, _, name = r["repository"]["nameWithOwner"].partition("/")
        out.append((owner, name))
    return out


def list_branches(owner, name):
    try:
        raw = json.loads(gh("api", "repos/%s/%s/branches?per_page=100" % (owner, name)))
        return [b["name"] for b in raw]
    except Exception:
        return ["main"]


def commits_on_branch(owner, name, branch, login):
    """某一分支上由 login 提交的全部 commit（sha -> 时间）。"""
    found = {}
    for page in range(1, 12):
        try:
            raw = json.loads(gh(
                "api",
                "repos/%s/%s/commits?sha=%s&per_page=100&page=%d" % (owner, name, branch, page),
                "--jq", '[.[] | {sha:.sha, date:.commit.author.date, login:(.author.login // "-")}]',
            ))
        except Exception:
            break
        if not raw:
            break
        for c in raw:
            if c["login"] == login:
                found[c["sha"]] = c["date"]
        if len(raw) < 100:
            break
    return found


def main():
    login = os.environ.get("GH_LOGIN", "yinghuajiai")
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)

    repos = list_repos(login)
    print("扫描 %d 个仓库" % len(repos))

    seen = {}          # sha -> iso 时间
    scanned = []       # 记录实际扫到东西的仓库
    for owner, name in repos:
        branches = list_branches(owner, name)
        got = 0
        for b in branches:
            cs = commits_on_branch(owner, name, b, login)
            got += len(cs)
            for sha, ts in cs.items():
                seen.setdefault(sha, ts)
        if got:
            scanned.append("%s/%s" % (owner, name))
            print("  %-34s %d 个分支 · %d 条提交" % ("%s/%s" % (owner, name), len(branches), got))

    # 按北京时间分桶到「日 → 24 小时」
    days = defaultdict(lambda: [0] * 24)
    for ts in seen.values():
        t = datetime.fromisoformat(ts.replace("Z", "+00:00")) + timedelta(hours=TZ_OFFSET)
        days[t.date().isoformat()][t.hour] += 1

    out = {
        "timezone": "Asia/Shanghai (UTC+8)",
        "offset_hours": TZ_OFFSET,
        "days": {d: v for d, v in sorted(days.items())},
        "total": sum(sum(v) for v in days.values()),
        "source_repos": scanned,
        "scanned_commits": len(seen),
    }

    path = os.path.join(root, "hourly.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    print()
    print("去重提交 %d 条 · 覆盖 %d 天" % (out["total"], len(days)))
    peak = sorted(
        ((d, sum(v)) for d, v in days.items()), key=lambda x: -x[1]
    )[:5]
    for d, n in peak:
        print("  %s  %d 次" % (d, n))
    print("写出", path)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
