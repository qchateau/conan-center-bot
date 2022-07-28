import os
import re
import typing
import inspect
import logging
import importlib.util

from conans import ConanFile

from .version import Version
from .upstream_project import get_upstream_project
from .utils import return_on_exc
from .cci import cci_interface
from .yaml import yaml


logger = logging.getLogger(__name__)


def get_recipes_list(cci_path):
    return os.listdir(os.path.join(cci_path, "recipes"))


class RecipeError(RuntimeError):
    pass


class LibPullRequest(typing.NamedTuple):
    library: str
    version: Version
    url: str
    number: int


class Recipe:
    def __init__(self, cci_path, name):
        self.name = name
        self.path = os.path.join(cci_path, "recipes", name)
        self.config_path = os.path.join(self.path, "config.yml")

    @property
    def supported(self):
        return os.path.exists(self.config_path)

    def config(self):
        if not os.path.exists(self.config_path):
            raise RecipeError("No config.yml file")

        with open(self.config_path) as fil:
            return yaml.load(fil)

    def versions(self):
        try:
            return [Version(v) for v in self.config()["versions"].keys()]
        except RecipeError as exc:
            logger.debug("%s: could not find versions: %s", self.name, exc)
            return []

    def most_recent_version(self):
        versions = self.versions()
        if not versions:
            return Version()
        return sorted(versions)[-1]

    def folder(self, version):
        assert isinstance(version, Version)

        for k, v in self.config()["versions"].items():
            if Version(k) == version:
                return v["folder"]
        raise KeyError(version)

    def for_version(self, version):
        return VersionedRecipe(self, version)


class VersionedRecipe:
    def __init__(self, recipe, version):
        assert isinstance(recipe, Recipe)
        self._recipe = recipe
        self.name = recipe.name
        self.path = recipe.path
        self.config_path = recipe.config_path
        self.version = version
        self.__upstream = None
        self.__conanfile_class = None

    @property
    def folder(self):
        return self._recipe.folder(self.version)

    @property
    def folder_path(self):
        return os.path.join(self.path, self.folder)

    @property
    def cmakelists_path(self):
        return os.path.join(self.folder_path, "test_package", "CMakeLists.txt")

    @property
    def conandata_path(self):
        return os.path.join(self.folder_path, "conandata.yml")

    @property
    def conanfile_path(self):
        return os.path.join(self.folder_path, "conanfile.py")

    @property
    def supported(self):
        return (
            self._recipe.supported
            and os.path.exists(self.conandata_path)
            and os.path.exists(self.conanfile_path)
        )

    @property
    @return_on_exc(logger, None)
    def homepage(self):
        if not self.supported:
            return None
        return self.conanfile_class().homepage

    @property
    @return_on_exc(logger, False)
    def deprecated(self):
        if not self.supported:
            return False
        return getattr(self.conanfile_class(), "deprecated", False)

    def upstream(self):
        if self.__upstream is None:
            self.__upstream = get_upstream_project(self)
        return self.__upstream

    def config(self):
        return self._recipe.config()

    def conandata(self):
        if not os.path.exists(self.conandata_path):
            raise RecipeError("no conandata.yml")
        with open(self.conandata_path) as fil:
            return yaml.load(fil)

    def source(self):
        conandata = self.conandata()
        for k, v in conandata["sources"].items():
            if Version(k) == self.version:
                return v
        raise KeyError(self.version)

    def conanfile_class(self):
        if self.__conanfile_class is None:
            if not os.path.exists(self.conanfile_path):
                raise RecipeError("no conanfile.py")

            spec = importlib.util.spec_from_file_location(
                "conanfile", self.conanfile_path
            )
            conanfile = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(conanfile)

            conanfile_main_class = None
            for symbol_name in dir(conanfile):
                symbol = getattr(conanfile, symbol_name)
                if (
                    inspect.isclass(symbol)
                    and issubclass(symbol, ConanFile)
                    and symbol is not ConanFile
                ):
                    conanfile_main_class = symbol
                    break

            if conanfile_main_class is None:
                raise RecipeError("Could not find ConanFile class")

            self.__conanfile_class = conanfile_main_class
        return self.__conanfile_class

    async def prs_opened_for(self, upstream_version: Version):
        body_re = re.compile(self.name + r"/" + upstream_version.fixed)
        title_re = re.compile(self.name + r".*" + upstream_version.fixed)

        return [
            LibPullRequest(
                library=self.name,
                version=upstream_version.fixed,
                url=pr["html_url"],
                number=pr["number"],
            )
            for pr in await cci_interface.pull_requests()
            if body_re.search(pr.get("body") or "")
            or title_re.search(pr.get("title") or "")
        ]

    async def upstream_version(self):
        upstream_versions = await self.upstream().versions()
        for version in upstream_versions:
            if version == self.version:
                return version
        logger.debug("%s: cannot get version meta (no match in upstream)", self.name)
        return Version(fixer=lambda _: self.version.original, meta=self.version.meta)
