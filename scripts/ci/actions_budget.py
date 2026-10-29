#!/usr/bin/env python3
"""Read-only Actions minute budget reporter (issue #680).

Idea adapted from the per-task and per-month spend caps in OpenADLC
(Apache-2.0, https://github.com/620legal/OpenADLC). No code was copied.

It never changes anything. It answers two questions:

  * How many billed-eligible (private-repo) minutes were used this month, and
    is that below the warn and stop thresholds in .github/actions-budget.json?
  * Which workflow jobs have no ``timeout-minutes`` (a runaway job has no cap)?

Exit codes: 0 ok or warn, 2 stop threshold crossed, 3 jobs without a timeout
(only with --check-timeouts).

Usage:
  GITHUB_TOKEN=... python3 scripts/ci/actions_budget.py --live --year 2026 --month 10
  python3 scripts/ci/actions_budget.py --usage-file usage.json --private-repo name ...
  python3 scripts/ci/actions_budget.py --check-timeouts
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONFIG = ROOT / ".github" / "actions-budget.json"
API = "https://api.github.com"


def load_config(path: pathlib.Path = CONFIG) -> dict:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    if not 0 < cfg["warn_at_percent"] < cfg["stop_at_percent"] <= 100:
        raise ValueError("need 0 < warn_at_percent < stop_at_percent <= 100")
    return cfg


def multiplier(sku: str, multipliers: dict) -> int:
    for key, value in multipliers.items():
        if key.lower() in sku.lower():
            return value
    return 1


def private_minutes(items: list, private_repos: set, multipliers: dict) -> dict:
    """Minutes per private repo, with the runner multiplier applied."""
    out: dict = {}
    for item in items:
        if item.get("product") != "actions" or item.get("unitType") != "Minutes":
            continue
        repo = item.get("repositoryName")
        if repo not in private_repos:
            continue
        minutes = item["quantity"] * multiplier(item.get("sku", ""), multipliers)
        out[repo] = out.get(repo, 0) + minutes
    return out


def classify(total: float, cfg: dict) -> str:
    pct = 100 * total / cfg["monthly_private_minutes_included"]
    if pct >= cfg["stop_at_percent"]:
        return "stop"
    if pct >= cfg["warn_at_percent"]:
        return "warn"
    return "ok"


def jobs_without_timeout(workflow_text: str) -> list:
    """Job ids under ``jobs:`` that have no job-level timeout-minutes."""
    lines = workflow_text.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if re.match(r"^jobs:\s*$", ln))
    except StopIteration:
        return []
    blocks: list = []
    for ln in lines[start + 1:]:
        if ln and not ln.startswith(" ") and not ln.startswith("#"):
            break
        match = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", ln)
        if match:
            blocks.append([match.group(1), False])
        elif blocks and re.match(r"^    timeout-minutes:\s*\S", ln):
            blocks[-1][1] = True
    return [name for name, has in blocks if not has]


def check_timeouts(workflows_dir: pathlib.Path) -> dict:
    result = {}
    for path in sorted(workflows_dir.glob("*.yml")):
        missing = jobs_without_timeout(path.read_text(encoding="utf-8"))
        if missing:
            result[path.name] = missing
    return result


def _get(url: str, token: str):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def live_inputs(token: str, year: int, month: int):
    user = _get(f"{API}/user", token)["login"]
    usage = _get(f"{API}/users/{user}/settings/billing/usage?year={year}&month={month}", token)
    repos = _get(f"{API}/user/repos?visibility=private&affiliation=owner&per_page=100", token)
    return usage["usageItems"], {r["name"] for r in repos}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--live", action="store_true", help="read usage with GITHUB_TOKEN")
    ap.add_argument("--year", type=int)
    ap.add_argument("--month", type=int)
    ap.add_argument("--usage-file", help="saved billing usage JSON")
    ap.add_argument("--private-repo", action="append", default=[])
    ap.add_argument("--check-timeouts", action="store_true")
    args = ap.parse_args(argv)
    cfg = load_config()
    code = 0

    if args.live or args.usage_file:
        if args.live:
            token = os.environ.get("GITHUB_TOKEN", "")
            if not token or not (args.year and args.month):
                ap.error("--live needs GITHUB_TOKEN, --year and --month")
            items, private = live_inputs(token, args.year, args.month)
        else:
            items = json.loads(pathlib.Path(args.usage_file).read_text())["usageItems"]
            private = set(args.private_repo)
        per_repo = private_minutes(items, private, cfg["minute_multipliers"])
        total = sum(per_repo.values())
        state = classify(total, cfg)
        print(f"private-repo minutes: {total:.0f} of {cfg['monthly_private_minutes_included']} ({state})")
        for repo, minutes in sorted(per_repo.items(), key=lambda kv: -kv[1]):
            print(f"  {repo}: {minutes:.0f}")
        if state == "stop":
            print("STOP: monthly cap reached. Do not start more private-repo runs; ask the owner.")
            code = 2
        elif state == "warn":
            print("WARN: past the warn threshold. Prefer local test runs; report to the owner.")

    if args.check_timeouts:
        missing = check_timeouts(ROOT / ".github" / "workflows")
        for name, jobs in missing.items():
            print(f"no timeout-minutes: {name}: {', '.join(jobs)}")
        print(f"{sum(len(j) for j in missing.values())} job(s) without timeout-minutes")
        if missing and code == 0:
            code = 3
    return code


if __name__ == "__main__":
    sys.exit(main())
