import re
import typing
import logging
import requests
import functools
from .github import get_github_token
from .version import Version


PR_REGEX = re.compile(r"Specify library name and version:[\s\*]*(.*)/([^\s]+)")


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

    @functools.lru_cache
    def libraries_pull_requests(self):
        prs = self.pull_requests()
        lib_prs = dict()
        for pr in prs:
            match = PR_REGEX.search(pr.get("body", ""))
            print(pr.get("body", ""))
            if not match:
                continue
            name = match.group(1)
            version = Version(match.group(2))
            lib_prs[name] = LibPullRequest(name, version, pr)
        return lib_prs


cci_interface = _CciInterface()
