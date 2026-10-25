# -*- coding: utf-8 -*-
"""
从 GitHub 拉取本账号的真实活动数据，写成 data.json。

数据源（全部已实测可用）：
  · contributionsCollection.commitContributionsByRepository
      → 每个仓库每天提交数（含 fork 仓库，GitHub 已按 OID 去重）
  · search(type: PR, author:...)  → PR 的开启日 / 合并日
  · REST /user/repos              → 仓库元信息（描述、语言、star、fork）

为什么要分月窗口：contributionsCollection 一次最多一年，但按仓库聚合的结果
在长窗口里会被截断，按月拉最稳。
"""
import json
import os
import subprocess
import sys
from collections import defaultdict
from datetime import date, timedelta

GH = "gh"


def gh(*args, timeout=90):
    p = subprocess.run(
        [GH, *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**os.environ, "NO_COLOR": "1", "GH_NO_UPDATE_NOTIFIER": "1"},
        timeout=timeout,
    )
    if p.returncode != 0:
        raise RuntimeError("gh %s 失败: %s" % (" ".join(args[:3]), (p.stderr or "").strip()[:300]))
    return p.stdout.strip()


def graphql(query):
    return json.loads(gh("api", "graphql", "-f", "query=" + query))


def month_windows(first, today):
    """按月切片，返回 [(start, end_exclusive)]"""
    out = []
    cur = date(first.year, first.month, 1)
    while cur <= today:
        nxt = date(cur.year + (cur.month == 12), (cur.month % 12) + 1, 1)
        out.append((cur, nxt))
        cur = nxt
    return out


def fetch_day_repo(login, first, today):
    day_repo = defaultdict(lambda: defaultdict(int))
    for start, end in month_windows(first, today):
        q = """
        query {
          user(login: "%s") {
            contributionsCollection(from: "%sT00:00:00Z", to: "%sT00:00:00Z") {
              commitContributionsByRepository(maxRepositories: 100) {
                repository { nameWithOwner }
                contributions(first: 100) {
                  nodes { occurredAt commitCount }
                }
              }
            }
          }
        }""" % (login, start.isoformat(), end.isoformat())
        data = graphql(q)["data"]["user"]["contributionsCollection"]
        for repo in data["commitContributionsByRepository"]:
            name = repo["repository"]["nameWithOwner"].split("/")[1]
            for node in repo["contributions"]["nodes"]:
                day_repo[node["occurredAt"][:10]][name] += node["commitCount"]
    return day_repo


def fetch_prs(login):
    q = """
    query {
      search(query: "author:%s type:pr", type: ISSUE, first: 100) {
        nodes {
          ... on PullRequest {
            number
            createdAt
            mergedAt
            state
            repository { nameWithOwner }
          }
        }
      }
    }""" % login
    return graphql(q)["data"]["search"]["nodes"]


def fetch_repos(login):
    # 注意：不能用 "user/repos"（= 当前认证账号的仓库）。
    # 在 Actions 里 GITHUB_TOKEN 是本仓库的 installation token，
    # 访问账号级接口会 403 Resource not accessible by integration。
    # 用公开的 /users/{login}/repos 即可。
    raw = json.loads(gh("api", "users/%s/repos?per_page=100&sort=pushed" % login))
    return [
        {
            "name": r["name"],
            "full_name": r["full_name"],
            "description": r["description"],
            "language": r["language"],
            "stars": r["stargazers_count"],
            "fork": r["fork"],
            "topics": r.get("topics") or [],
            "license": (r.get("license") or {}).get("spdx_id"),
            "created": r["created_at"][:10],
            "pushed": r["pushed_at"][:10],
        }
        for r in raw
    ]


def main():
    login = os.environ.get("GH_LOGIN", "yinghuajiai")

    # 账号实际的建号日，而不是写死
    profile = json.loads(gh("api", "users/" + login))
    born = date.fromisoformat(profile["created_at"][:10])
    today = date.today()

    print("账号 %s，建号 %s，今天 %s" % (login, born, today))

    day_repo = fetch_day_repo(login, born, today)
    prs = fetch_prs(login)
    try:
        repos = fetch_repos(login)
    except Exception as e:
        print("警告：仓库元信息获取失败（不影响图表）：%s" % e)
        repos = []

    commits = sum(sum(v.values()) for v in day_repo.values())
    print("提交 %d 次 · 活跃 %d 天 · PR %d 个" % (commits, len(day_repo), len(prs)))

    out = {
        "login": login,
        "generated_at": today.isoformat(),
        "born": born.isoformat(),
        "day_repo": {d: dict(v) for d, v in sorted(day_repo.items())},
        "prs": [
            {
                "number": p["number"],
                "repo": p["repository"]["nameWithOwner"],
                "createdAt": p["createdAt"],
                "mergedAt": p["mergedAt"],
                "state": p["state"],
            }
            for p in prs
        ],
        "repos": repos,
    }

    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    path = os.path.join(root, "data.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, sort_keys=False)
    print("写出", path)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
