import os
import timeit
import logging
import subprocess
from ruamel.yaml import YAML
from ruamel.yaml.constructor import DoubleQuotedScalarString

from .recipe import Recipe, RecipeError, get_recipes_list
from .status import get_status
from .worktree import RecipeInWorktree


logger = logging.getLogger(__name__)


class UpdateError(RuntimeError):
    pass


class RecipeNotSupported(UpdateError):
    pass


class RecipeDeprecated(RecipeNotSupported):
    pass


class UpstreamNotSupported(UpdateError):
    pass


class RecipeNotUpdatable(UpdateError):
    pass


class TestFailed(UpdateError):
    def __init__(self, complete_process):
        super().__init__("test failed")


class BranchAlreadyExists(UpdateError):
    def __init__(self, branch_name):
        super().__init__(f"branch already exists: {branch_name}")
        self.branch_name = branch_name


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


def remote_branch_exists(recipe, branch_name, remote):
    return (
        subprocess.call(
            [
                "git",
                "show-ref",
                "--verify",
                "-q",
                f"refs/remotes/{remote}/{branch_name}",
            ],
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
        logger.error(f"conandata.yml file not found: {conandata_path}")
        raise RecipeNotSupported("no conandata.yml")

    url = recipe.upstream.source_url(upstream_version)
    hash_digest = recipe.upstream.source_sha256_digest(upstream_version)

    config = recipe.config()
    config["versions"][DoubleQuotedScalarString(conan_version)] = {}
    config["versions"][conan_version]["folder"] = folder

    conandata_yaml = YAML()
    conandata_yaml.preserve_quotes = True
    with open(conandata_path) as fil:
        conandata = conandata_yaml.load(fil)
    conandata["sources"][DoubleQuotedScalarString(conan_version)] = {}
    conandata["sources"][conan_version]["url"] = DoubleQuotedScalarString(url)
    conandata["sources"][conan_version]["sha256"] = DoubleQuotedScalarString(
        hash_digest
    )

    with open(recipe.config_file_path, "w") as fil:
        recipe.config_yaml.dump(config, fil)

    with open(conandata_path, "w") as fil:
        conandata_yaml.dump(conandata, fil)


def test_recipe(recipe, folder, version_str):
    version_folder_path = os.path.join(recipe.path, folder)

    env = os.environ.copy()
    env["CONAN_HOOK_ERROR_LEVEL"] = "40"

    ret = subprocess.run(
        ["conan", "create", ".", f"{recipe.name}/{version_str}@"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=version_folder_path,
    )

    logger.debug(ret.stdout.decode())

    if ret.returncode != 0:
        if not logger.isEnabledFor(logging.DEBUG):
            logger.info(ret.stdout.decode())
        raise TestFailed(ret)


def _get_most_recent_upstream_version(recipe):
    status = recipe.status()

    if status.up_to_date():
        raise RecipeNotUpdatable("recipe is up-to-date")

    if not status.update_possible():
        raise RecipeNotUpdatable("update is not possible")

    upstream_version = status.upstream_version
    if upstream_version.unknown:
        raise UpstreamNotSupported("upstream version is unknown")
    return upstream_version


def _get_user_choice_upstream_version(recipe):
    recipe_versions_fixed = [v.fixed for v in recipe.versions]
    versions = list(
        sorted(
            v for v in recipe.upstream.versions if v.fixed not in recipe_versions_fixed
        )
    )
    if not versions:
        raise UpstreamNotSupported("no upstream versions found")

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
    cci_path,
    recipe_name,
    choose_version,
    folder,
    run_test,
    push_to,
    force,
    allow_interaction,
):
    recipe = Recipe(cci_path, recipe_name)
    if getattr(recipe.conanfile_class, "deprecated", False):
        raise RecipeDeprecated("recipe is deprecated")

    if choose_version:
        upstream_version = _get_user_choice_upstream_version(recipe)
    else:
        upstream_version = _get_most_recent_upstream_version(recipe)

    conan_version = upstream_version.fixed
    branch_name = f"{recipe.name}-{conan_version}"
    force_push = force

    if branch_exists(recipe, branch_name):
        if allow_interaction and not force:
            force = yn_question(
                f"Branch '{branch_name}' already exists, overwrite ?", False
            )
        if not force:
            raise BranchAlreadyExists(branch_name)
        remove_branch(recipe, branch_name)

    if remote_branch_exists(recipe, branch_name, push_to):
        if allow_interaction and not force_push:
            force_push = yn_question(
                f"Remote branch '{push_to}/{branch_name}' already exists, overwrite ?",
                False,
            )
        if not force_push:
            raise BranchAlreadyExists(f"{push_to}/{branch_name}")

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
            new_recipe,
            branch_name,
            f"{recipe.name}: add version {conan_version}\n\n"
            "Generated and committed by [conan-center-bot](https://github.com/qchateau/conan-center-bot)",
        )

        if push_to:
            logger.info("%s: pushing", recipe_name)
            push_branch(new_recipe, push_to, branch_name, force_push)

    logger.info(
        "%s: created version %s in branch %s (%s)",
        recipe_name,
        conan_version,
        branch_name,
        "pushed" if push_to else "not pushed",
    )

    return branch_name


def update_recipes(
    cci_path,
    recipes,
    choose_version,
    folder,
    run_test,
    push_to,
    force,
    allow_interaction,
):
    ok = True
    for recipe in recipes:
        try:
            update_one_recipe(
                cci_path,
                recipe,
                choose_version,
                folder,
                run_test,
                push_to,
                force,
                allow_interaction,
            )
        except (RecipeNotUpdatable, RecipeDeprecated) as exc:
            logger.info("%s: skipped (%s)", recipe, str(exc))
        except (UpdateError, RecipeError) as exc:
            logger.error("%s: %s", recipe, str(exc))
            ok = False

    return 0 if ok else 1
