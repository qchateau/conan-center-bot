import os
import yaml
import inspect
import subprocess
import importlib.util
from functools import cached_property, lru_cache

from conans import ConanFile

from .exceptions import RecipeError
from .version import Version
from .upstream_project import get_upstream_project


def get_recipes_list(cci_path):
    return os.listdir(os.path.join(cci_path, "recipes"))


class Recipe:
    def __init__(self, cci_path, name):
        self.name = name
        self.path = os.path.join(cci_path, "recipes", name)
        self.config_file_path = os.path.join(self.path, "config.yml")
        if not os.path.exists(self.config_file_path):
            raise RecipeError("No config.yml file")

    @cached_property
    def upstream(self):
        return get_upstream_project(self)

    @property
    def config(self):
        with open(self.config_file_path) as fil:
            return yaml.load(fil, Loader=yaml.FullLoader)

    @property
    def versions_folders(self):
        return {Version(k): v["folder"] for k, v in self.config["versions"].items()}

    @property
    def most_recent_version(self):
        return sorted(self.versions_folders.keys())[-1]

    @lru_cache
    def conanfile_class(self, version):
        assert isinstance(version, Version)

        version_folder_path = os.path.join(self.path, self.versions_folders[version])

        spec = importlib.util.spec_from_file_location(
            "conanfile", os.path.join(version_folder_path, "conanfile.py")
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

        return conanfile_main_class

    def version_exists(self, version):
        return version.fixed in self.config["versions"]

    def add_version(self, folder, version, url, digest):
        assert isinstance(version, Version)

        conandata_path = os.path.join(self.path, folder, "conandata.yml")
        if not os.path.exists(conandata_path):
            raise RecipeError(f"No conandata.yml in {folder}")

        with open(conandata_path) as fil:
            conandata = yaml.load(fil, Loader=yaml.FullLoader)

        config = self.config.copy()
        config["versions"][version.fixed] = {"folder": folder}
        conandata["sources"][version.fixed] = {"sha256": digest, "url": url}

        with open(self.config_file_path, "w") as fil:
            yaml.dump(config, fil)

        with open(conandata_path, "w") as fil:
            yaml.dump(conandata, fil)

    def test(self, version):
        assert isinstance(version, Version)

        version_folder_path = os.path.join(self.path, self.versions_folders[version])

        env = os.environ.copy()
        env["CONAN_HOOK_ERROR_LEVEL"] = "40"

        subprocess.check_output(
            ["conan", "create", ".", f"{self.name}/{version.fixed}@"],
            env=env,
            cwd=version_folder_path,
            stderr=subprocess.STDOUT,
        )
