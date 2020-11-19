import re
import time
import datetime
import logging
import traceback
import requests

from . import __version__
from .recipe import get_recipes_list
from .status import get_status
from .github import get_github_token
from .update import update_one_recipe, BranchAlreadyExists, TestFailed
from .cci import cci_interface


ISSUE_URL_RE = re.compile(r"github.com/([^/]+)/([^/]+)/issues/([0-9]+)")
logger = logging.getLogger(__name__)


def _format_duration(duration):
    hours = int(duration // 3600)
    duration -= hours * 3600
    minutes = int(duration // 60)
    seconds = duration - minutes * 60

    if hours > 0:
        return f"{hours}h {minutes}m"
    if minutes > 0:
        return f"{minutes}m {int(seconds)}s"
    return f"{seconds:.1f}s"


def _update_issue(issue_url, content):
    match = ISSUE_URL_RE.search(issue_url)
    if not match:
        logger.error("update failed: bad issue URL")
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

    logger.error("update failed: %s", resp.reason)
    return False


def update_status_issue(  # pylint:disable=too-many-locals
    cci_path,
    issue_url_list,
    branch_prefix,
    force,
    push_to,
    status_jobs,
):
    t0 = time.time()
    recipes = get_recipes_list(cci_path)
    status = get_status(cci_path, recipes, status_jobs)
    status = [s for s in status if not s.deprecated]
    status = list(sorted(status, key=lambda s: s.name))
    updatable = [s for s in status if s.update_possible()]
    inconsistent_version = [s for s in status if s.inconsistent_versioning()]
    up_to_date_count = len([s for s in status if s.up_to_date()])
    unsupported_count = (
        len(status) - len(updatable) - len(inconsistent_version) - up_to_date_count
    )

    logger.info("fetching opened PRs")
    cci_interface.pull_requests()

    errors = dict()
    branches = dict()
    durations = dict()
    for i, recipe_status in enumerate(updatable):
        print(
            f"===== [{i+1:3}/{len(updatable):3}] {' '+recipe_status.name+' ':=^25}====="
        )

        if recipe_status.prs_opened():
            logger.info("%s: skipped (PR exists)", recipe_status.name)
            continue

        try:
            t1 = time.time()
            branches[recipe_status] = update_one_recipe(
                cci_path=cci_path,
                recipe_name=recipe_status.name,
                choose_version=False,
                folder=None,
                run_test=True,
                push_to=push_to,
                force=force,
                allow_interaction=False,
                branch_prefix=branch_prefix,
            )
        except BranchAlreadyExists as exc:
            logger.info("%s: skipped (%s)", recipe_status.name, str(exc))
            branches[recipe_status] = exc.branch_name
        except TestFailed as exc:
            logger.error("%s: test failed", recipe_status.name)
            durations[recipe_status] = time.time() - t1
            errors[recipe_status] = exc.details()
        except Exception as exc:
            logger.error("%s: %s", recipe_status.name, str(exc))
            durations[recipe_status] = time.time() - t1
            errors[recipe_status] = traceback.format_exc()
        else:
            durations[recipe_status] = time.time() - t1

        if recipe_status in durations:
            logger.info(
                "%s: took %s",
                recipe_status.name,
                _format_duration(durations[recipe_status]),
            )

    duration = time.time() - t0

    def make_pr_text(status):
        prs = status.prs_opened()
        if prs:
            return ", ".join([f"[#{pr.number}]({pr.url})" for pr in prs])

        branch = branches.get(status)
        if branch is not None:
            owner, repo = cci_interface.owner_and_repo(cci_path)
            return f"[Open one](https://github.com/{owner}/{repo}/pull/new/{branch})"

        return "No"

    def make_duration_text(status):
        if status not in durations:
            return "skipped"
        return _format_duration(durations[status])

    def str_to_pre(err):
        return "<pre>" + err.replace("\n", "<br/>") + "</pre>"

    date = datetime.datetime.now().strftime("%d/%m/%Y")
    text = "\n".join(
        [
            "# Conan Center Bot",
            "",
            f"* Date: {date}",
            f"* Parsed recipes: {len(recipes)}",
            f"* Up-to-date recipes: {up_to_date_count}",
            f"* Updatable recipes: {len(updatable)}",
            f"* Inconsistent recipes: {len(inconsistent_version)}",
            f"* Unsupported recipes: {unsupported_count}",
            f"* Duration: {_format_duration(duration)}",
            f"* Version: {__version__}",
            "",
            "This list is auto-generated by [Conan Center Bot](https://github.com/qchateau/conan-center-bot) "
            "and the updatability detection or version parsing can be flawed. Any help improving "
            "this tool is welcome !",
            "",
            "You can also use [Conan Center Bot](https://github.com/qchateau/conan-center-bot) "
            "to automatically generate an update for a recipe.",
            "",
            "### Updatable recipes" "",
            "|Name|Recipe version|New version|Upstream version|Pull request|Duration|",
            "|----|--------------|-----------|----------------|------------|--------|",
        ]
        + [
            "|".join(
                [
                    "",
                    f"[{s.name}]({s.homepage})" if s.homepage else f"{s.name}",
                    f"{s.recipe_version}",
                    f"{s.upstream_version.fixed}",
                    f"{s.upstream_version}",
                    make_pr_text(s),
                    make_duration_text(s),
                    "",
                ]
            )
            for s in updatable
        ]
        + [
            "",
            "### Inconsistent recipes",
            "",
            "The following recipes are not consistent with their upstream versioning scheme. "
            "Most of the times it means the current recipe version is not related to any upstream tag.",
            "",
            "|Name|Current recipe version|Upstream version|",
            "|----|----------------------|----------------|",
        ]
        + [
            "|".join(
                [
                    "",
                    f"[{s.name}]({s.homepage})" if s.homepage else f"{s.name}",
                    f"{s.recipe_version}",
                    f"{s.upstream_version}",
                    "",
                ]
            )
            for s in inconsistent_version
        ]
        + [
            "",
            "### Updatable recipes with errors",
            "",
            "The following recipes are detected as updatable but the bot "
            "failed to automatically update the recipe."
            "",
            "<table>",
            "<tr><th>Name</th><th>Error</th></tr>",
        ]
        + [
            "<tr><td>"
            + (f'<a href="{s.homepage}">{s.name}</a>' if s.homepage else f"{s.name}")
            + "</td>"
            + "<td>"
            + f"{str_to_pre(error)}"
            + "</td>"
            + "</tr>"
            for s, error in errors.items()
        ]
    )

    if issue_url_list:
        ok = True
        for issue_url in issue_url_list:
            this_ok = _update_issue(issue_url, text)
            if this_ok:
                print(f"Updated {issue_url}")
            ok = ok and this_ok
    else:
        print(text)
        ok = True

    return 0 if ok else 1
