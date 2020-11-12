import os
import yaml
import logging
import subprocess

from .recipe import Recipe, RecipeError
from .worktree import RecipeInWorktree


logger = logging.getLogger(__name__)


class _Skip(RuntimeError):
    pass


class _Failure(RuntimeError):
    pass


class _TestFailed(_Failure):
    def __init__(self, output):
        super().__init__("test failed")
        self.output = output


def yn_question(question, default):
    default_txt = "[Y/n]" if default else "[y/N]"
    while True:
        txt = input(f"{question} {default_txt} ").strip().lower()
        if not txt:
            return default
        elif txt[0] == "y":
            return True
        elif txt[0] == "n":
            return False


def branch_exists(recipe, branch_name):
    return (
        subprocess.call(
            ["git", "show-ref", "--verify", "-q", f"refs/heads/{branch_name}"],
            cwd=recipe.path,
        )
        == 0
    )


def create_branch_and_commit(recipe, branch_name, commit_msg):
    subprocess.check_call(["git", "checkout", "-q", "-b", branch_name], cwd=recipe.path)
    subprocess.check_call(
        [
            "git",
            "commit",
            "-q",
            "-a",
            "-m",
            commit_msg,
        ],
        cwd=recipe.path,
    )


def remove_branch(recipe, branch_name):
    subprocess.check_call(["git", "branch", "-q", "-D", branch_name], cwd=recipe.path)


def push_branch(recipe, remote, branch_name, force):
    subprocess.check_output(
        ["git", "push", "-q", "--set-upstream"]
        + (["-f"] if force else [])
        + [remote, branch_name],
        cwd=recipe.path,
    )


def add_version(recipe, folder, conan_version, upstream_version):
    conandata_path = os.path.join(recipe.path, folder, "conandata.yml")
    if not os.path.exists(conandata_path):
        raise _Failure("no conandata.yml")

    with open(conandata_path) as fil:
        conandata = yaml.load(fil, Loader=yaml.FullLoader)

    url = recipe.upstream.source_url(upstream_version)
    hash_digest = recipe.upstream.source_sha256_digest(upstream_version)
    config = recipe.config()
    config["versions"][conan_version] = {"folder": folder}
    conandata["sources"][conan_version] = {"sha256": hash_digest, "url": url}

    with open(recipe.config_file_path, "w") as fil:
        yaml.dump(config, fil)

    with open(conandata_path, "w") as fil:
        yaml.dump(conandata, fil)


def test_recipe(recipe, folder, version_str):
    version_folder_path = os.path.join(recipe.path, folder)

    env = os.environ.copy()
    env["CONAN_HOOK_ERROR_LEVEL"] = "40"

    if not logger.isEnabledFor(logging.DEBUG):
        stdout = stderr = subprocess.DEVNULL
    else:
        stdout = stderr = None

    code = subprocess.call(
        ["conan", "create", ".", f"{recipe.name}/{version_str}@"],
        env=env,
        stdout=stdout,
        stderr=stderr,
        cwd=version_folder_path,
    )

    if code != 0:
        raise _Failure("test failed")


def _get_most_recent_upstream_version(recipe):
    status = recipe.status()

    if status.up_to_date():
        raise _Skip("recipe is up-to-date")

    if not status.update_possible():
        raise _Failure("update is not possible")

    upstream_version = status.upstream_version
    if upstream_version.unknown:
        raise _Failure("upstream version is unknown")
    return upstream_version


def _get_user_choice_upstream_version(recipe):
    recipe_versions_fixed = [v.fixed for v in recipe.versions]
    versions = list(
        sorted(
            v for v in recipe.upstream.versions if v.fixed not in recipe_versions_fixed
        )
    )
    if not versions:
        raise _Failure("update is not possible")

    print("Choose an upstream version:")
    for i, v in enumerate(versions):
        print(f"{i:3d}) {v}")

    upstream_version = None
    while upstream_version is None:
        try:
            upstream_version = versions[int(input("Choice: "))]
        except (ValueError, KeyError):
            pass
    return upstream_version


def update_one_recipe(
    cci_path, recipe_name, choose_version, folder, run_test, push, force
):
    recipe = Recipe(cci_path, recipe_name)
    if getattr(recipe.conanfile_class, "deprecated", False):
        raise _Skip("recipe is deprecated")

    if choose_version:
        upstream_version = _get_user_choice_upstream_version(recipe)
    else:
        upstream_version = _get_most_recent_upstream_version(recipe)

    conan_version = upstream_version.fixed
    branch_name = f"{recipe.name}-{conan_version}"
    if branch_exists(recipe, branch_name):
        if not force:
            force = yn_question(
                f"Branch '{branch_name}' already exists, overwrite ?", False
            )
        if not force:
            raise _Failure(f"branch '{branch_name}' already exists")
        remove_branch(recipe, branch_name)

    folder = folder or recipe.versions_folders[recipe.most_recent_version]

    logger.info(
        "%s: adding version %s to folder %s in branch %s from upstream version %s",
        recipe_name,
        conan_version,
        folder,
        branch_name,
        upstream_version,
    )

    with RecipeInWorktree(recipe) as new_recipe:
        add_version(new_recipe, folder, conan_version, upstream_version)

        if run_test:
            logger.info("%s: running test", recipe_name)
            test_recipe(new_recipe, folder, conan_version)

        create_branch_and_commit(
            new_recipe, branch_name, f"{recipe.name}: add version {conan_version}"
        )

        if push:
            logger.info("%s: pushing", recipe_name)
            push_branch(new_recipe, "origin", branch_name, force)

    logger.info(
        "%s: created version %s in branch %s (%s)",
        recipe_name,
        conan_version,
        branch_name,
        "pushed" if push else "not pushed",
    )


def update_recipes(cci_path, recipes, choose_version, folder, run_test, push, force):
    ok = True
    for recipe in recipes:
        try:
            update_one_recipe(
                cci_path, recipe, choose_version, folder, run_test, push, force
            )
        except _Skip as exc:
            logger.info("%s: skipped (%s)", recipe, str(exc))
        except (_Failure, RecipeError) as exc:
            logger.error("%s: %s", recipe, str(exc))
            ok = False

    return 0 if ok else 1
