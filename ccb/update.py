import os
import re
import copy
import json
import time
import typing
import datetime
import logging
import traceback
import subprocess
import multiprocessing

from . import __version__
from .recipe import Recipe, RecipeError, get_recipes_list
from .worktree import RecipeInWorktree
from .yaml import yaml, DoubleQuotes
from .version import Version
from .cci import cci_interface
from .utils import format_duration
from .status import get_status


logger = logging.getLogger(__name__)
mp_lock = multiprocessing.Lock()


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
    RE_ERRORS = [
        re.compile(r"^\[HOOK.*\].*:\s*ERROR:\s*(.*)$", re.M),
        re.compile(r"^ERROR:.*(Error in.*)", re.M | re.S),
        re.compile(r"^ERROR:.*(Invalid configuration.*)", re.M | re.S),
        re.compile(r"^ERROR:\s*(.*)", re.M | re.S),
    ]

    def __init__(self, complete_process):
        super().__init__("Test failed")
        self.complete_process = complete_process

    @property
    def output(self):
        return self.complete_process.stdout.decode()

    def details(self):
        for regex in self.RE_ERRORS:
            errors = [match.group(1) for match in regex.finditer(self.output)]
            if errors:
                return "\n".join(errors)
        return "no details"


class BranchAlreadyExists(UpdateError):
    def __init__(self, branch_name, remote=None):
        super().__init__(
            f"branch already exists: {remote+'/' if remote else ''}{branch_name}"
        )
        self.branch_name = branch_name
        self.remote = remote


class UpdateStatus(typing.NamedTuple):
    branch_name: typing.Optional[str] = None
    branch_remote_owner: typing.Optional[str] = None
    branch_remote_repo: typing.Optional[str] = None
    error: typing.Optional[str] = None


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
    most_recent_version = recipe.most_recent_version.original
    url = recipe.upstream.source_url(upstream_version)
    hash_digest = recipe.upstream.source_sha256_digest(upstream_version)

    def smart_insert(container, key, value):
        container_keys = list(container.keys())
        ascending = Version(container_keys[0]) < Version(container_keys[-1])
        insert_idx = len(container_keys)
        if ascending:
            for idx, ckey in enumerate(container_keys):
                if Version(ckey) > Version(key):
                    insert_idx = idx
                    break
            container.insert(insert_idx, key, value)
        else:
            for idx, ckey in enumerate(container_keys):
                if Version(ckey) < Version(key):
                    insert_idx = idx
                    break
            container.insert(insert_idx, key, value)

    config = recipe.config()
    smart_insert(config["versions"], DoubleQuotes(conan_version), {})
    config["versions"][conan_version]["folder"] = folder

    conandata = recipe.conandata(folder)
    smart_insert(conandata["sources"], DoubleQuotes(conan_version), {})
    conandata["sources"][conan_version]["url"] = DoubleQuotes(url)
    conandata["sources"][conan_version]["sha256"] = DoubleQuotes(hash_digest)

    most_recent_patches = conandata.get("patches", {}).get(most_recent_version)
    if most_recent_patches:
        smart_insert(
            conandata["patches"],
            DoubleQuotes(conan_version),
            copy.deepcopy(most_recent_patches),
        )

    with open(recipe.config_path, "w") as fil:
        yaml.dump(config, fil)

    with open(recipe.conandata_path(folder), "w") as fil:
        yaml.dump(conandata, fil)


def test_recipe(recipe, folder, version_str):
    t0 = time.time()
    logger.info("%s: running test", recipe.name)

    version_folder_path = os.path.join(recipe.path, folder)

    env = os.environ.copy()
    env["CONAN_HOOK_ERROR_LEVEL"] = "40"

    ret = subprocess.run(
        ["conan", "create", ".", f"{recipe.name}/{version_str}@"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=version_folder_path,
        check=False,
    )

    logger.debug(ret.stdout.decode())
    logger.info("%s: test took %s", recipe.name, format_duration(time.time() - t0))

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
    recipe,
    upstream_version,
    folder,
    run_test,
    push_to,
    force,
    allow_interaction,
    branch_prefix,
):
    assert isinstance(recipe, Recipe)

    if getattr(recipe.conanfile_class, "deprecated", False):
        raise RecipeDeprecated("recipe is deprecated")

    conan_version = upstream_version.fixed
    branch_name = f"{branch_prefix}{recipe.name}-{conan_version}"
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
            raise BranchAlreadyExists(branch_name, push_to)

    folder = folder or recipe.folder(recipe.most_recent_version)

    logger.info(
        "%s: adding version %s to folder %s in branch %s from upstream version %s",
        recipe.name,
        conan_version,
        folder,
        branch_name,
        upstream_version,
    )

    with RecipeInWorktree(recipe) as new_recipe:
        add_version(new_recipe, folder, conan_version, upstream_version)

        if run_test:
            with mp_lock:
                test_recipe(new_recipe, folder, conan_version)

        create_branch_and_commit(
            new_recipe,
            branch_name,
            f"{recipe.name}: add version {conan_version}\n\n"
            "Generated and committed by [conan-center-bot](https://github.com/qchateau/conan-center-bot)",
        )

        if push_to:
            logger.info("%s: pushing", recipe.name)
            push_branch(new_recipe, push_to, branch_name, force_push)

    logger.info(
        "%s: created version %s in branch %s (%s)",
        recipe.name,
        conan_version,
        branch_name,
        "pushed" if push_to else "not pushed",
    )

    return branch_name


def _auto_update_one_recipe(recipe_name, cci_path, branch_prefix, force, push_to):
    recipe = Recipe(cci_path, recipe_name)
    recipe_status = recipe.status()

    if recipe_status.prs_opened():
        logger.info("%s: skipped (PR exists)", recipe.name)
        return UpdateStatus(None, None, None, None)

    error = branch_name = branch_remote_owner = branch_remote_repo = None
    try:
        branch_name = update_one_recipe(
            recipe=recipe,
            upstream_version=recipe_status.upstream_version,
            folder=None,
            run_test=True,
            push_to=push_to,
            force=force,
            allow_interaction=False,
            branch_prefix=branch_prefix,
        )
        if push_to:
            branch_remote_owner, branch_remote_repo = cci_interface.owner_and_repo(
                cci_path,
                push_to,
            )
    except BranchAlreadyExists as exc:
        logger.info("%s: skipped (%s)", recipe.name, str(exc))
        branch_name = exc.branch_name
        if exc.remote:
            branch_remote_owner, branch_remote_repo = cci_interface.owner_and_repo(
                cci_path,
                exc.remote,
            )
    except TestFailed as exc:
        logger.error("%s: test failed", recipe.name)
        error = exc.details()
    except Exception as exc:
        logger.error("%s: %s", recipe.name, str(exc))
        error = traceback.format_exc()
    return UpdateStatus(branch_name, branch_remote_owner, branch_remote_repo, error)


def _auto_update_recipes(recipe_names, cci_path, branch_prefix, force, push_to, jobs):
    with multiprocessing.Pool(jobs) as p:
        futures = [
            p.apply_async(
                _auto_update_one_recipe,
                args=(recipe_name, cci_path, branch_prefix, force, push_to),
            )
            for recipe_name in recipe_names
        ]

        return {
            recipe_name: fut.get() for recipe_name, fut in zip(recipe_names, futures)
        }


def auto_update_all_recipes(cci_path, branch_prefix, force, push_to, jobs):
    t0 = time.time()
    recipes = get_recipes_list(cci_path)
    status = get_status(cci_path, recipes, jobs)
    status = [s for s in status if not s.deprecated]
    status = list(sorted(status, key=lambda s: s.name))
    updatable = [s for s in status if s.update_possible()]

    logger.info("fetching opened PRs")
    cci_interface.pull_requests()

    update_status = _auto_update_recipes(
        [s.name for s in updatable],
        cci_path,
        branch_prefix,
        force,
        push_to,
        jobs,
    )

    duration = time.time() - t0

    def _generate_recipe_update_status(status):
        update = update_status.get(status.name, UpdateStatus())
        return {
            "name": status.name,
            "homepage": status.homepage,
            "recipe_version": status.recipe_version.original,
            "upstream_version": status.upstream_version.fixed,
            "upstream_tag": status.upstream_version.original,
            "deprecated": status.deprecated,
            "inconsistent_versioning": status.inconsistent_versioning(),
            "updatable": status.update_possible(),
            "up_to_date": status.up_to_date(),
            "supported": not status.deprecated
            and status.update_possible()
            or status.up_to_date(),
            "prs_opened": [
                {
                    "number": pr.number,
                    "url": pr.url,
                }
                for pr in status.prs_opened()
            ],
            "updated_branch": {
                "owner": update.branch_remote_owner,
                "repo": update.branch_remote_repo,
                "branch": update.branch_name,
            },
            "update_error": update.error,
        }

    status = {
        "date": datetime.datetime.now().isoformat(),
        "duration": duration,
        "ccb_version": __version__,
        "recipes": [_generate_recipe_update_status(s) for s in status],
    }
    print(json.dumps(status))
    return 0


def manual_update_recipes(
    cci_path,
    recipes,
    choose_version,
    folder,
    run_test,
    push_to,
    force,
    allow_interaction,
    branch_prefix,
):
    ok = True
    for recipe_name in recipes:
        try:
            recipe = Recipe(cci_path, recipe_name)

            if choose_version:
                upstream_version = _get_user_choice_upstream_version(recipe)
            else:
                upstream_version = _get_most_recent_upstream_version(recipe)

            update_one_recipe(
                recipe,
                upstream_version,
                folder,
                run_test,
                push_to,
                force,
                allow_interaction,
                branch_prefix,
            )
        except (RecipeNotUpdatable, RecipeDeprecated) as exc:
            logger.info("%s: skipped (%s)", recipe, str(exc))
        except TestFailed as exc:
            logger.error("%s: Test failed:\n%s", recipe, exc.details())
        except (UpdateError, RecipeError) as exc:
            logger.error("%s: %s", recipe, str(exc))
            ok = False

    return 0 if ok else 1
