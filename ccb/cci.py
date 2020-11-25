import re
import logging
import aiohttp

from .github import get_github_token
from .subprocess import check_output
from .utils import LockStorage

logger = logging.getLogger(__name__)
pr_lock = LockStorage()


class _CciInterface:
    def __init__(self):
        self.owner = "conan-io"
        self.repo = "conan-center-index"
        self.__pull_requests = None

    async def pull_requests(self):
        async with pr_lock.get():
            if self.__pull_requests is None:
                github_token = get_github_token()
                headers = {"Accept": "application/vnd.github.v3+json"}
                if github_token:
                    headers["Authorization"] = f"token {github_token}"
                url = f"https://api.github.com/repos/{self.owner}/{self.repo}/pulls"

                prs = list()

                page = 1
                async with aiohttp.ClientSession(raise_for_status=True) as client:
                    while True:
                        logger.debug("getting PR page %s", page)
                        params = {"page": str(page), "per_page": "100"}
                        async with client.get(
                            url, params=params, headers=headers
                        ) as resp:
                            results = await resp.json()
                        prs.extend(results)
                        page += 1

                        logger.debug("%s results", len(results))
                        if not results:
                            break
                self.__pull_requests = prs

            return self.__pull_requests

    @staticmethod
    async def owner_and_repo(cci_path, remote):
        pattern = re.compile(r"[/:]([^/]+)/([^/]+)\.git")
        origin = await check_output(
            ["git", "config", "--get", f"remote.{remote}.url"], cwd=cci_path
        )

        return pattern.search(origin).groups()


cci_interface = _CciInterface()
