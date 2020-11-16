import re
import typing
import logging
import requests
import functools
from .github import get_github_token
from .version import Version

logger = logging.getLogger(__name__)


class LibPullRequest(typing.NamedTuple):
    library: str
    version: Version
    pr: typing.Any


class _CciInterface:
    def __init__(self):
        self.owner = "conan-io"
        self.repo = "conan-center-index"

    @functools.lru_cache
    def pull_requests(self):
        github_token = get_github_token()
        headers = {"Accept": "application/vnd.github.v3+json"}
        if github_token:
            headers["Authorization"] = f"token {github_token}"
        url = f"https://api.github.com/repos/{self.owner}/{self.repo}/pulls"

        prs = list()

        page = 1
        while True:
            logger.debug("getting PR page %s", page)
            params = {"page": str(page), "per_page": "100"}
            res = requests.get(url, params=params, headers=headers)
            res.raise_for_status()
            results = res.json()
            prs.extend(results)
            page += 1

            logger.debug("%s results", len(results))
            if not results:
                break

        return prs

    def pull_request_for(self, recipe_status):
        body_re = re.compile(
            recipe_status.name + r"/" + recipe_status.upstream_version.fixed
        )
        title_re = re.compile(
            recipe_status.name + r".*" + recipe_status.upstream_version.fixed
        )

        return [
            pr
            for pr in self.pull_requests()
            if body_re.search(pr.get("body", ""))
            or title_re.search(pr.get("title", ""))
        ]


cci_interface = _CciInterface()
