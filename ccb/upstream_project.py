import re
import abc
import hashlib
import requests
import logging
import tempfile
import subprocess
from functools import cached_property, lru_cache

from .version import Version


logger = logging.getLogger(__name__)


class _Unsupported(RuntimeError):
    pass


def get_upstream_project(recipe):
    conanfile_class = recipe.conanfile_class(recipe.most_recent_version)
    for cls in _CLASSES:
        try:
            return cls(recipe, conanfile_class)
        except _Unsupported:
            pass

    logger.warn("%s: unsupported upstream", recipe.name)
    return UnsupportedProject(recipe, conanfile_class)


class UpstreamProject(abc.ABC):
    def __init__(self, recipe, conanfile_class):
        self.recipe = recipe
        self.conanfile_class = conanfile_class

    @abc.abstractproperty
    def versions(self) -> dict:
        pass

    @abc.abstractproperty
    def most_recent_version(self) -> Version:
        pass

    @abc.abstractmethod
    def source_url(self, version) -> str:
        pass

    @lru_cache
    def source_sha256_digest(self, version):
        url = self.source_url(version)
        if not url:
            return None
        sha256 = hashlib.sha256()
        tarball = requests.get(url)
        sha256.update(tarball.content)
        return sha256.hexdigest()


class UnsupportedProject(UpstreamProject):
    @cached_property
    def versions(self):
        return {}

    @property
    def most_recent_version(self):
        return Version()

    def source_url(self, version):
        return None


class GitProject(UpstreamProject):
    def __init__(self, recipe, conanfile_class, git_url):
        super().__init__(recipe, conanfile_class)
        self.git_url = git_url

    @cached_property
    def versions(self):
        git_output = subprocess.check_output(
            ["git", "ls-remote", "-t", self.git_url]
        ).decode()
        tags = [ref.replace("refs/tags/", "") for ref in git_output.split()[1::2]]
        logger.info(f"Found: {tags}")

        return tuple(Version(tag) for tag in tags)

    @property
    def most_recent_version(self):
        if not self.versions:
            return Version()
        return sorted(self.versions)[-1]


class GithubProject(GitProject):
    HOMEPAGE_RE = re.compile(r"https://github.com/([^/]+)/([^/]+)")

    def __init__(self, recipe, conanfile_class):
        match = self.HOMEPAGE_RE.match(conanfile_class.homepage)
        if not match:
            raise _Unsupported()

        owner = match.group(1)
        repo = match.group(2)
        git_url = f"https://github.com/{owner}/{repo}.git"

        super().__init__(recipe, conanfile_class, git_url)
        self.owner = owner
        self.repo = repo

    def source_url(self, version):
        if version.unknown:
            return None
        return f"https://github.com/{self.owner}/{self.repo}/archive/{version.original}.tar.gz"


_CLASSES = [GithubProject]
