import re
import os
import abc
import time
import typing
import datetime
import tempfile
import hashlib
import traceback
import logging
import aiohttp

from .version import Version, VersionMeta
from .project_specifics import (
    TAGS_BLACKLIST,
    PROJECT_TAGS_BLACKLIST,
    PROJECT_TAGS_WHITELIST,
    PROJECT_TAGS_FIXERS,
)
from .subprocess import check_output, check_call
from .utils import SemaphoneStorage, format_duration
from .github import get_github_token


logger = logging.getLogger(__name__)


class _Unsupported(RuntimeError):
    pass


clone_sem = SemaphoneStorage(int(os.environ.get("CCB_CLONE_CONCURRENCY", "3")))


def get_upstream_project(recipe):
    for cls in _CLASSES:
        try:
            return cls(recipe)
        except _Unsupported:
            pass

    logger.debug("%s: unsupported upstream", recipe.name)
    return UnsupportedProject(recipe)


class UpstreamProject(abc.ABC):
    def __init__(self, recipe):
        self.recipe = recipe
        self.__sha256 = {}

    @property
    def homepage(self) -> str:
        return self.recipe.homepage

    @abc.abstractmethod
    async def versions(self) -> list:
        pass

    async def most_recent_version(self) -> Version:
        versions = await self.versions()
        if not versions:
            return Version()
        return sorted(versions)[-1]

    @abc.abstractmethod
    def source_url(self, version) -> str:
        pass

    async def source_sha256_digest(self, version):
        if version not in self.__sha256:
            url = self.source_url(version)
            if not url:
                return None
            sha256 = hashlib.sha256()
            async with aiohttp.ClientSession(raise_for_status=True) as client:
                async with client.get(url) as resp:
                    async for data in resp.content.iter_any():
                        sha256.update(data)
            self.__sha256[version] = sha256.hexdigest()
        return self.__sha256[version]


class UnsupportedProject(UpstreamProject):
    async def versions(self):
        return []

    def source_url(self, version):
        return None


class GitProject(UpstreamProject):
    class _TagData(typing.NamedTuple):
        name: str
        commit_count: int
        date: typing.Optional[datetime.datetime] = None

    def __init__(self, recipe, git_url):
        super().__init__(recipe)
        self.git_url = git_url
        self.whitelist = PROJECT_TAGS_WHITELIST.get(recipe.name, [])
        self.blacklist = TAGS_BLACKLIST + PROJECT_TAGS_BLACKLIST.get(recipe.name, [])
        self.fixer = PROJECT_TAGS_FIXERS.get(recipe.name, None)
        self.__versions = None

    async def versions(self):
        if self.__versions is None:
            try:
                await self._clone_and_parse_git_repo()
            except Exception as exc:
                logger.info("%s: error parsing repository: %s", self.recipe.name, exc)
                logger.debug(traceback.format_exc())
                self.__versions = list()
        return self.__versions

    async def _clone_and_parse_git_repo(self):
        async with clone_sem.get():
            t0 = time.time()
            with tempfile.TemporaryDirectory(prefix=f"ccb-{self.recipe.name}") as tmp:
                logger.info("%s: cloning repository %s", self.recipe.name, self.git_url)
                env = os.environ.copy()
                env["GIT_TERMINAL_PROMPT"] = "0"
                await check_call(
                    ["git", "clone", "-q", "--filter=tree:0", "-n", self.git_url, tmp],
                    env=env,
                )
                logger.info("%s: parsing repository", self.recipe.name)
                await self._parse_git_repo(tmp)
            duration = time.time() - t0
            logger.info(
                "%s: parsed repository in %s",
                self.recipe.name,
                format_duration(duration),
            )

    async def _parse_git_repo(self, git_dir):
        tags_data = await self._parse_tags(git_dir)
        logger.debug(
            "%s: found tags: %s",
            self.recipe.name,
            [t.name for t in tags_data],
        )

        self.__versions = list()
        for tag_data in tags_data:
            meta = VersionMeta(date=tag_data.date, commit_count=tag_data.commit_count)
            self.__versions.append(
                Version(version=tag_data.name, fixer=self.fixer, meta=meta)
            )

    async def _parse_tags(self, git_dir) -> typing.List[_TagData]:
        output = await check_output(
            [
                "git",
                "for-each-ref",
                "--format",
                "%(refname) %(taggerdate)%(committerdate)",
                "refs/tags",
            ],
            cwd=git_dir,
        )

        tag_data = list()

        for line in output.splitlines():
            ref, date = line.split(" ", 1)
            tag = ref[10:]

            if not self._valid_tags(tag):
                continue

            try:
                date = datetime.datetime.strptime(date, "%c %z")
            except ValueError as exc:
                logger.debug(
                    "%s: ignored tag '%s' date: %s",
                    self.recipe.name,
                    tag,
                    exc,
                )
                date = None

            # don't gather, that's way too many sub-processes
            commit_count = await self._count_commits(ref, git_dir)

            tag_data.append(self._TagData(tag, commit_count, date))

        return tag_data

    @staticmethod
    async def _count_commits(ref, git_dir):
        output = await check_output(["git", "rev-list", "--count", ref], cwd=git_dir)
        return int(output)

    def _valid_tags(self, tag):
        if self.whitelist:
            if any(regex.match(tag) for regex in self.whitelist):
                return True
            else:
                logger.debug(
                    "%s: tag %s ignored because it does not match any of %s",
                    self.recipe.name,
                    tag,
                    list(regex.pattern for regex in self.whitelist),
                )
                return False
        else:
            for regex in self.blacklist:
                if regex.match(tag):
                    logger.debug(
                        "%s: tag %s ignored because it matches regex %s",
                        self.recipe.name,
                        tag,
                        regex.pattern,
                    )
                    return False
            return True


class GithubProject(GitProject):
    HOMEPAGE_RE = re.compile(r"https?://github.com/([^/]+)/([^/]+)")
    SOURCE_URL_RE = re.compile(r"https?://github.com/([^/]+)/([^/]+)")

    def __init__(self, recipe):
        owner, repo = self._get_owner_repo(recipe)
        git_url = f"https://github.com/{owner}/{repo}.git"

        super().__init__(recipe, git_url)
        self.owner = owner
        self.repo = repo
        self.__versions = None

    async def versions(self):
        if self.__versions is None:
            try:
                github_token = get_github_token()
                headers = {"Accept": "application/vnd.github.v3+json"}
                if github_token:
                    headers["Authorization"] = f"token {github_token}"
                async with aiohttp.ClientSession(raise_for_status=True, headers=headers) as client:
                    async with client.get(
                        f"https://api.github.com/repos/{self.owner}/{self.repo}/releases"
                    ) as resp:                          
                        def _get_url_for_version(v):
                            artifacts = v["assets"]
                            for a in artifacts:
                                if a["content_type"] == "application/x-xz":
                                    return a["browser_download_url"]
                            for a in artifacts:
                                if a["content_type"] == "application/x-gzip":
                                    return a["browser_download_url"]
                            for a in artifacts:
                                if a["content_type"] == "application/gzip":
                                    return a["browser_download_url"]
                            for a in artifacts:
                                if a["content_type"] == "application/x-bzip2":
                                    return a["browser_download_url"]
                            return f"https://github.com/{self.owner}/{self.repo}/archive/refs/tags/{v['tag_name']}.tar.gz"  
                        self.__versions = []
                        for v in await resp.json():
                            tag_name = v["tag_name"] or v["name"]
                            r = Version(tag_name, fixer=self.fixer)                        
                            if not self._valid_tags(tag_name):
                                continue
                            r.url = _get_url_for_version(v)
                            self.__versions.append(r)
                        
            except Exception as exc:
                logger.info("%s: error parsing repository: %s", self.recipe.name, exc)
                logger.debug(traceback.format_exc())
                self.__versions = []   
        if self.__versions:
            return self.__versions
        else:
            return await super().versions()


    def source_url(self, version):
        if version.unknown:
            return None
        if hasattr(version, "url"):
            return version.url
        return f"https://github.com/{self.owner}/{self.repo}/archive/{version.original}.tar.gz"

    @classmethod
    def _get_owner_repo(cls, recipe):
        try:
            url = recipe.source()["url"]
            match = cls.SOURCE_URL_RE.match(url)
            if match:
                return match.groups()
        except Exception as exc:
            logger.debug(
                "%s: not supported as GitHub project because of the following exception: %s",
                recipe.name,
                repr(exc),
            )

        raise _Unsupported()


class GitlabProject(GitProject):
    SOURCE_URL_RE = re.compile(
        r"https?://([^/]*gitlab[^/]+)/([^/]+)/([^/]+)/-/(?:archive|releases)/"
    )

    def __init__(self, recipe):
        domain, owner, repo = self._get_domain_owner_repo(recipe)
        git_url = f"https://{domain}/{owner}/{repo}.git"

        super().__init__(recipe, git_url)
        self.domain = domain
        self.owner = owner
        self.repo = repo
        self.__versions = None

    async def versions(self):
        if self.__versions is None:
            try:
                async with aiohttp.ClientSession(raise_for_status=True) as client:
                    async with client.get(
                        f"https://{self.domain}/api/v4/projects/{self.owner}%2F{self.repo}/releases"
                    ) as resp:
                        def _get_url_for_version(v):
                            artifacts = v["assets"]["links"]
                            for a in artifacts:
                                if a["direct_asset_url"].endswith(".tar.xz"):
                                    return a["direct_asset_url"]
                            for a in artifacts:
                                if a["direct_asset_url"].endswith(".tar.gz"):
                                    return a["direct_asset_url"]
                            for a in artifacts:
                                if a["direct_asset_url"].endswith(".tar.bz2"):
                                    return a["direct_asset_url"]
                            return f"https://{self.domain}/{self.owner}/{self.repo}/-/archive/{v['tag_name']}/{self.repo}-{v['tag_name']}.tar.gz"
                        self.__versions = []
                        for v in await resp.json():
                            tag_name = v["tag_name"] or v["name"]
                            r = Version(tag_name, fixer=self.fixer)
                            if not self._valid_tags(tag_name):
                                continue
                            r.url = _get_url_for_version(v)
                            self.__versions.append(r)
            except Exception as exc:
                logger.info("%s: error parsing repository: %s", self.recipe.name, exc)
                logger.debug(traceback.format_exc())
                self.__versions = []
        if self.__versions:
            return self.__versions
        else:
            return await super().versions()

    def source_url(self, version):
        if version.unknown:
            return None
        if hasattr(version, "url"):
            return version.url
        return f"https://{self.domain}/{self.owner}/{self.repo}/-/archive/{version.original}/{self.repo}-{version.original}.tar.gz"

    @classmethod
    def _get_domain_owner_repo(cls, recipe):
        try:
            url = recipe.source()["url"]
            match = cls.SOURCE_URL_RE.match(url)
            if match:
                return match.groups()
        except Exception as exc:
            logger.debug(
                "%s: not supported as Gitlab project because of the following exception: %s",
                recipe.name,
                repr(exc),
            )

        raise _Unsupported()


class GnomeProject(UpstreamProject):
    SOURCE_URL_RE = re.compile(
        r"https?://(download\.gnome\.org|ftp\.gnome\.org/pub/gnome)/sources/([^/]+)/"
    )

    def __init__(self, recipe):
        domain, project = self._get_project(recipe)
        super().__init__(recipe)
        self.domain = domain
        self.project = project
        self.__versions = None

    @classmethod
    def _get_project(cls, recipe):
        try:
            url = recipe.source()["url"]
            match = cls.SOURCE_URL_RE.match(url)
            if match:
                return match.groups()
        except Exception as exc:
            logger.debug(
                "%s: not supported as Gnome project because of the following exception: %s",
                recipe.name,
                repr(exc),
            )
        raise _Unsupported()

    async def versions(self):
        if self.__versions is None:
            try:
                async with aiohttp.ClientSession(raise_for_status=True) as client:
                    async with client.get(
                        f"https://{self.domain}/sources/{self.project}/cache.json"
                    ) as resp:
                        d = await resp.json()
                        self.__versions = [Version(v) for v in d[2][self.project]]
            except Exception as exc:
                logger.info("%s: error parsing repository: %s", self.recipe.name, exc)
                logger.debug(traceback.format_exc())
                self.__versions = list()
        return self.__versions

    def source_url(self, version):
        if version.unknown:
            return None
        major, minor, patch = version.original.split(".")
        return f"https://{self.domain}/sources/{self.project}/{major}.{minor}/{self.project}-{major}.{minor}.{patch}.tar.xz"


_CLASSES = [GithubProject, GitlabProject, GnomeProject]
