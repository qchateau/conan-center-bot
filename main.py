import os
import re
import sys
import argparse
import inspect
import hashlib
import subprocess
import importlib.util
from multiprocessing import Pool

import yaml
import requests
from conans import ConanFile

RECIPES_PATH = None
GITHUB_HOMEPAGE_RE = re.compile(r"https://github.com/([^/]+)/([^/]+)")
VERSION_RE = re.compile(r"[0-9]+\.[0-9\.]+")
VERSION_DASH_RE = re.compile(r"[0-9]+-[0-9-]+")
VERSION_UNDERSCORE_RE = re.compile(r"[0-9]+_[0-9_]+")

GITHUB_TOKEN = None


class UnsupportedRecipe(RuntimeError):
    pass


def read_yaml(path):
    with open(path) as fil:
        return yaml.load(fil, Loader=yaml.FullLoader)


def recipe_path(recipe):
    return os.path.join(RECIPES_PATH, recipe)


def to_numeric_version(version):
    try:
        return tuple(int(x) for x in version.split("."))
    except (ValueError, AttributeError):
        return None


def fix_version(version):
    version = str(version)
    fixed_version = version

    while True:  # to break from
        match = VERSION_RE.search(version)
        if match:
            fixed_version = match.group(0)
            break

        match = VERSION_DASH_RE.search(version)
        if match:
            fixed_version = match.group(0).replace("-", ".")
            break

        match = VERSION_UNDERSCORE_RE.search(version)
        if match:
            fixed_version = match.group(0).replace("_", ".")
            break

        break

    return fixed_version


def most_recent_version(versions):
    most_recent = None
    most_recent_num = tuple()
    for version in versions:
        fixed_version = fix_version(version)
        vnum = to_numeric_version(fixed_version)
        if vnum and vnum > most_recent_num:
            most_recent_num = vnum
            most_recent = version
    return most_recent


def read_recipe_config(recipe):
    config_file_path = os.path.join(recipe_path(recipe), "config.yml")
    if not os.path.exists(config_file_path):
        raise UnsupportedRecipe(f"No config.yml file")

    config = read_yaml(config_file_path)
    return config


def find_recipe_most_recent_version(recipe):
    config = read_recipe_config(recipe)
    versions = list(config["versions"].keys())
    if len(versions) == 1:
        most_recent = versions[0]
    else:
        most_recent = most_recent_version(versions)
    if not most_recent:
        raise UnsupportedRecipe(f"Could not find most recent version")
    version_folder = config["versions"][most_recent]["folder"]
    return most_recent, version_folder


def read_conanfile_main_class(recipe, version):
    config = read_recipe_config(recipe)
    version_folder = config["versions"][version]["folder"]
    version_folder_path = os.path.join(recipe_path(recipe), version_folder)

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
        raise RuntimeError(f"Could not find ConanFile class")

    return conanfile_main_class


def get_github_api_headers():
    if GITHUB_TOKEN:
        return {"Authorization": f"token {GITHUB_TOKEN}"}
    else:
        return None


def find_most_recent_upstream_version_github(url):
    match = GITHUB_HOMEPAGE_RE.match(url)
    if not match:
        return None

    owner = match.group(1)
    repo = match.group(2)
    tags_url = f"https://api.github.com/repos/{owner}/{repo}/tags"

    resp = requests.get(tags_url, headers=get_github_api_headers())
    if not resp.ok:
        raise UnsupportedRecipe(f"Could not find tags: {resp.reason}")
    tags = {rel["name"]: rel for rel in resp.json()}
    versions = list(tags.keys())
    if not versions:
        raise UnsupportedRecipe("No upstream version")
    most_recent = most_recent_version(versions)
    if not most_recent:
        raise UnsupportedRecipe("Could not find most recent upstream version")
    tarball_url = f"https://github.com/{owner}/{repo}/archive/{most_recent}.tar.gz"
    return most_recent, tarball_url


def find_most_recent_upstream_version(recipe):
    version, _ = find_recipe_most_recent_version(recipe)
    conanfile = read_conanfile_main_class(recipe, version)
    homepage = conanfile.homepage

    github = find_most_recent_upstream_version_github(homepage)
    if github:
        return github

    raise UnsupportedRecipe("Only GitHub is supported")


def find_folder(recipe, version):
    # Ignore version for now, assume it's the most recent
    _, version_folder = find_recipe_most_recent_version(recipe)
    return version_folder


def add_version(recipe, version=None, folder=None, url=None, hash_digest=None):
    if not version or not url:
        found_version, found_url = find_most_recent_upstream_version(recipe)
        version = fix_version(found_version) if version is None else version
        url = found_url if url is None else url

        if not version:
            raise UnsupportedRecipe(f"Could not find most recent upstream version")
        if not url:
            raise UnsupportedRecipe(f"Could not find url")

    config = read_recipe_config(recipe)
    versions = list(config["versions"].keys())
    if version in versions:
        return None

    if not folder:
        folder = find_folder(recipe, version)

        if not folder:
            raise UnsupportedRecipe(f"Could not find folder")

    if not hash_digest:
        sha256 = hashlib.sha256()
        tarball = requests.get(url)
        sha256.update(tarball.content)
        hash_digest = sha256.hexdigest()

    add_version_to_config(recipe, version, folder)
    add_version_to_conandata(recipe, version, folder, url, hash_digest)
    return version


def test_recipe(recipe, version):
    config = read_recipe_config(recipe)
    version_folder = config["versions"][version]["folder"]
    version_folder_path = os.path.join(recipe_path(recipe), version_folder)
    env = os.environ.copy()
    env["CONAN_HOOK_ERROR_LEVEL"] = "40"

    subprocess.check_output(
        ["conan", "create", ".", f"{recipe}/{version}@"],
        env=env,
        cwd=version_folder_path,
        stderr=subprocess.STDOUT,
    )


def add_version_to_config(recipe, version, folder):
    config = read_recipe_config(recipe)
    config["versions"][version] = {"folder": folder}

    config_file_path = os.path.join(recipe_path(recipe), "config.yml")
    with open(config_file_path, "w") as fil:
        yaml.dump(config, fil)


def add_version_to_conandata(recipe, version, folder, url, hash_digest):
    config = read_recipe_config(recipe)
    version_folder = config["versions"][version]["folder"]
    version_folder_path = os.path.join(recipe_path(recipe), version_folder)
    conandata_path = os.path.join(version_folder_path, "conandata.yml")

    with open(conandata_path) as fil:
        conandata = yaml.load(fil, Loader=yaml.FullLoader)

    conandata["sources"][version] = {"sha256": hash_digest, "url": url}

    with open(conandata_path, "w") as fil:
        yaml.dump(conandata, fil)


def process_recipe(recipe, args):
    print(f"{recipe}...\r", end="")
    sys.stdout.flush()
    try:
        version = add_version(recipe)
        if version:
            print(f"{recipe:20}: new version")
            if args.test:
                try:
                    print(f"{recipe:20}: testing...\r", end="")
                    sys.stdout.flush()
                    test_recipe(recipe, version)
                except subprocess.CalledProcessError as exc:
                    print(f"{recipe:20}: test failed")
                    print(f"\n\n{exc.output.decode()}\n\n")

        else:
            print(f"{recipe:20}: skipped")
    except UnsupportedRecipe as e:
        print(f"{recipe:20}: unsupported ({str(e)[:50]})")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("conan_center_index_path")
    parser.add_argument("--recipe", nargs="*")
    parser.add_argument("--github-token")
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--processes", default=os.cpu_count() * 10)
    args = parser.parse_args()

    global RECIPES_PATH
    RECIPES_PATH = os.path.join(args.conan_center_index_path, "recipes")

    if args.github_token:
        global GITHUB_TOKEN
        GITHUB_TOKEN = args.github_token

    if args.recipe:
        recipes = args.recipe
    else:
        recipes = os.listdir(RECIPES_PATH)

    print(f"Using {len(recipes)} recipes")

    with Pool(args.processes) as p:
        results = [
            p.apply_async(process_recipe, args=(recipe, args)) for recipe in recipes
        ]
        for r in results:
            r.get()


if __name__ == "__main__":
    main()
