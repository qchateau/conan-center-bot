#!/usr/bin/env python3

import os
import re
import sys
import time
import datetime
import argparse
import requests

from ccb.status import get_status
from ccb.recipe import get_recipes_list


ROOT = os.path.dirname(os.path.realpath(__file__))
ISSUE_URL_RE = re.compile(r"github.com/([^/]+)/([^/]+)/issues/([0-9]+)")


def update_issue(owner, repo, issue_number, github_token, content):
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}"
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json",
    }
    data = {"body": content}
    resp = requests.patch(url, json=data, headers=headers)
    if resp.ok:
        return True

    print(f"update failed: {resp.reason}")
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("issue_url", help="URL of the issue to update")
    parser.add_argument("github_token", help="Github authentication token")
    parser.add_argument(
        "--cci",
        help="Path to the conan-center-index repository. Defaults to '../conan-center-index'",
    )
    parser.add_argument(
        "--jobs",
        "-j",
        default=str(10 * os.cpu_count()),
        help="Number of parallel processes.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Don't update the issue."
    )
    args = parser.parse_args()

    if not args.cci:
        args.cci = os.path.join(ROOT, "..", "conan-center-index")

    args.cci = os.path.abspath(args.cci)
    if not os.path.exists(args.cci):
        print(f"CCI repository not found at {args.cci}")
        sys.exit(1)

    match = ISSUE_URL_RE.search(args.issue_url)
    if not match:
        print("Bad issue URL")
        sys.exit(1)
    owner, repo, issue_number = match.groups()

    t0 = time.time()
    recipes = get_recipes_list(args.cci)
    status = get_status(args.cci, recipes, int(args.jobs))
    updatable = [s for s in status if s.update_possible()]
    duration = time.time() - t0

    date = datetime.datetime.now().strftime("%d/%m/%Y")
    text = "\n".join(
        [
            f"* Date: {date}",
            f"* Parsed recipes: {len(recipes)}",
            f"* Updatable recipes: {len(updatable)}",
            f"* Duration: {duration:.1f}s",
            "",
            "Keep in mind this list is auto-generated and the "
            "updatability detection can be flawed.",
            "",
            "You can use conan-center-bot at "
            "https://github.com/qchateau/conan-center-bot "
            "to automatically generate an update.",
            "",
            "|Name|Recipe version|Upstream version|",
            "|----|--------------|----------------|",
        ]
        + [
            f"|{s.name}|{s.recipe_version}|{s.upstream_version}|"
            for s in sorted(updatable, key=lambda s: s.name)
        ]
    )

    print(text)
    if not args.dry_run:
        ok = update_issue(owner, repo, issue_number, args.github_token, text)
    else:
        ok = True
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()