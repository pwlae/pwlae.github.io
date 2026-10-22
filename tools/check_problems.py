#!/usr/bin/env python3
"""Check every <leetcode> card in lessons/ against LeetCode's public API.

Usage: python3 tools/check_problems.py [lesson-id ...]

Fails if a slug does not exist, or the number, title or difficulty is wrong,
or the problem is premium-only (most commuters do not have premium).
"""
import json
import re
import sys
import time
import urllib.request
from html import unescape
from pathlib import Path

LESSONS = Path(__file__).resolve().parent.parent / "lessons"
QUERY = "query($s:String!){question(titleSlug:$s){questionFrontendId title difficulty isPaidOnly}}"


def fetch(slug):
    body = json.dumps({"query": QUERY, "variables": {"s": slug}}).encode()
    req = urllib.request.Request(
        "https://leetcode.com/graphql",
        data=body,
        headers={"Content-Type": "application/json", "Referer": "https://leetcode.com", "User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)["data"]["question"]


def main(ids):
    files = [LESSONS / f"{i}.html" for i in ids] if ids else sorted(LESSONS.glob("*.html"))
    bad = 0
    for f in files:
        for tag in re.findall(r"<leetcode([^>]*)>", f.read_text()):
            a = {k: unescape(v) for k, v in re.findall(r'([\w-]+)="([^"]*)"', tag)}
            q = fetch(a.get("slug", ""))
            time.sleep(0.3)
            problems = []
            if not q:
                problems.append("slug not found")
            else:
                if q["questionFrontendId"] != a.get("num"):
                    problems.append(f"num should be {q['questionFrontendId']}")
                if q["title"] != a.get("title"):
                    problems.append(f'title should be "{q["title"]}"')
                if q["difficulty"] != a.get("level"):
                    problems.append(f"level should be {q['difficulty']}")
                if q["isPaidOnly"]:
                    problems.append("premium-only, pick a free problem")
            status = "ok" if not problems else "; ".join(problems)
            bad += bool(problems)
            print(f"{f.stem:16} {a.get('slug')}: {status}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main(sys.argv[1:])
