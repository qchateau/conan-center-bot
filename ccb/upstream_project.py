import re
import hashlib
import requests

from .recipe import Recipe
from .config import get_github_token
from .version import Version
from .exceptions import UnsupportedUpstreamProject


def get_upstream_project(recipe: Recipe):
    conanfile_class = recipe.conanfile_class(recipe.most_recent_version)
    for cls in _CLASSES:
        if cls.supports(conanfile_class):
            return cls(recipe)
    raise UnsupportedUpstreamProject(
        f"Cannot handle project at {conanfile_class.homepage}"
    )


class GithubProject:
    HOMEPAGE_RE = re.compile(r"https://github.com/([^/]+)/([^/]+)")

    @classmethod
    def supports(cls, conanfile_class):
        return bool(cls.HOMEPAGE_RE.match(conanfile_class.homepage))

    def __init__(self, recipe: Recipe):
        self.recipe = recipe

        self.conanfile_class = self.recipe.conanfile_class(
            self.recipe.most_recent_version
        )

        match = self.HOMEPAGE_RE.match(self.conanfile_class.homepage)
        self.owner = match.group(1)
        self.repo = match.group(2)

        self.__versions = None
        self.__tarball_digests = dict()

    @property
    def versions(self):
        if self.__versions is None:
            tags_url = f"https://api.github.com/repos/{self.owner}/{self.repo}/tags"

            resp = requests.get(tags_url, headers=_get_github_api_headers())
            if not resp.ok:
                raise UnsupportedUpstreamProject(f"Could not find tags: {resp.reason}")
            self.__versions = tuple(Version(rel["name"]) for rel in resp.json())
        return self.__versions

    @property
    def most_recent_version(self):
        return sorted(self.versions)[-1]

    def tarball_url(self, version):
        return f"https://github.com/{self.owner}/{self.repo}/archive/{version.original}.tar.gz"

    def tarball_sha256_digest(self, version):
        if version not in self.__tarball_digests:
            sha256 = hashlib.sha256()
            tarball = requests.get(self.tarball_url(version))
            sha256.update(tarball.content)
            self.__tarball_digests[version] = sha256.hexdigest()
        return self.__tarball_digests[version]


def _get_github_api_headers():
    token = get_github_token()
    if token:
        return {"Authorization": f"token {token}"}
    else:
        return None


_CLASSES = [GithubProject]