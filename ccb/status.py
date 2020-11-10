import re
import json
import time
import logging
import datetime
from multiprocessing import Pool

import requests
from terminaltables import AsciiTable
from colored import fg, stylize

from .recipe import get_recipes_list, Recipe
from .version import Version
from .github import get_github_token

ISSUE_URL_RE = re.compile(r"github.com/([^/]+)/([^/]+)/issues/([0-9]+)")
logger = logging.getLogger(__name__)


def status_one_recipe(cci_path, recipe_name):
    return Recipe(cci_path, recipe_name).status()


def get_status(cci_path, recipes, jobs):
    logger.info(f"Parsing {len(recipes)} recipes...")

    with Pool(jobs) as p:
        status_futures = [
            p.apply_async(status_one_recipe, args=(cci_path, recipe))
            for recipe in recipes
        ]
        return [f.get() for f in status_futures]


def update_issue(issue_url, content):
    match = ISSUE_URL_RE.search(issue_url)
    if not match:
        logger.error(f"update failed: bad issue URL")
        return False

    owner, repo, issue_number = match.groups()
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}"
    github_token = get_github_token()
    headers = {"Accept": "application/vnd.github.v3+json"}
    if github_token:
        headers["Authorization"] = f"token {github_token}"
    data = {"body": content}
    resp = requests.patch(url, json=data, headers=headers)
    if resp.ok:
        return True

    logger.error(f"update failed: {resp.reason}")
    return False


def print_status_table(cci_path, recipes, print_all, jobs):
    status = get_status(cci_path, recipes, jobs)
    table_data = [
        ["Name", "Recipe version", "New version", "Upstream version", "Pending PR"]
    ]
    for s in sorted(status, key=lambda r: r.name):
        if s.recipe_version.unknown or s.upstream_version.unknown:
            name_color = fg("red")
        elif s.update_possible():
            name_color = fg("dark_orange")
        else:
            name_color = fg("green")

        if not s.update_possible() and not print_all:
            continue

        pr = s.pr_opened()
        pr_text = "Yes" if pr else "No"

        rv_color = fg("green") if not s.recipe_version.unknown else fg("red")
        uv_color = fg("green") if not s.upstream_version.unknown else fg("red")
        pr_color = fg("green") if pr else fg("dark_orange")

        table_data.append(
            [
                stylize(s.name, name_color),
                stylize(s.recipe_version, rv_color),
                stylize(s.upstream_version.fixed, uv_color),
                stylize(s.upstream_version, uv_color),
                stylize(pr_text, pr_color),
            ]
        )

    table = AsciiTable(table_data)
    print(table.table)
    return 0


def update_status_issue(cci_path, issue_url_list, jobs, dry_run):
    t0 = time.time()
    recipes = get_recipes_list(cci_path)
    status = get_status(cci_path, recipes, jobs)
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
            "|Name|Recipe version|New version|Upstream version|Pending PR|",
            "|----|--------------|-----------|----------------|----------|",
        ]
        + [
            "|".join(
                [
                    "",
                    f"[{s.name}]({s.homepage})" if s.homepage else f"{s.name}",
                    f"{s.recipe_version}",
                    f"{s.upstream_version.fixed}",
                    f"{s.upstream_version}",
                    f"[Yes]({s.pr_opened()['html_url']})" if s.pr_opened() else "No",
                    "",
                ]
            )
            for s in sorted(updatable, key=lambda s: s.name)
        ]
    )

    print(text)
    if not dry_run:
        ok = True
        for issue_url in issue_url_list:
            ok = update_issue(issue_url, text) and ok
    else:
        ok = True

    return 0 if ok else 1
