import os
import re
import copy
import json
import time
import typing
import asyncio
import logging
import datetime
import traceback
import subprocess

from .recipe import Recipe, RecipeError, get_recipes_list
from .worktree import RecipeInWorktree
from .yaml import yaml, DoubleQuotes
from .version import Version
from .cci import cci_interface
from .utils import format_duration
from .status import get_status
from .subprocess import run, call, check_call


logger = logging.getLogger(__name__)

RE_TEST_ERRORS = [
    re.compile(r"^\[HOOK.*\].*:\s*ERROR:\s*(.*)$", re.M),
    re.compile(r"^ERROR:.*(Error in.*)", re.M | re.S),
    re.compile(r"^ERROR:.*(Invalid configuration.*)", re.M | re.S),
    re.compile(r"^ERROR:\s*(.*)", re.M | re.S),
]


class UpdateError(RuntimeError):
    pass


class UpstreamNotSupported(UpdateError):
    pass


class RecipeNotUpdatable(UpdateError):
    pass


class TestStatus(typing.NamedTuple):
    success: bool
    duration: float
    error: typing.Optional[str] = None


class UpdateStatus(typing.NamedTuple):
    updated: bool
    test_status: typing.Optional[TestStatus] = None
    branch_name: typing.Optional[str] = None
    branch_remote_owner: typing.Optional[str] = None
    branch_remote_repo: typing.Optional[str] = None
    details: typing.Optional[str] = None


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


def get_test_details(output):
    for regex in RE_TEST_ERRORS:
        errors = [match.group(1) for match in regex.finditer(output)]
        if errors:
            return "\n".join(errors)
    return "no details"


async def branch_exists(recipe, branch_name):
    return (
        await call(
            ["git", "show-ref", "--verify", "-q", f"refs/heads/{branch_name}"],
            cwd=recipe.path,
        )
        == 0
    )


async def remote_branch_exists(recipe, branch_name, remote):
    return (
        await call(
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


async def create_branch_and_commit(recipe, branch_name, commit_msg):
    await check_call(["git", "checkout", "-q", "-b", branch_name], cwd=recipe.path)
    await check_call(
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


async def remove_branch(recipe, branch_name):
    await check_call(["git", "branch", "-q", "-D", branch_name], cwd=recipe.path)


async def push_branch(recipe, remote, branch_name, force):
    await check_call(
        ["git", "push", "-q", "--set-upstream"]
        + (["-f"] if force else [])
        + [remote, branch_name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=recipe.path,
    )


async def add_version(recipe, folder, conan_version, upstream_version):
    most_recent_version = recipe.most_recent_version().original
    url = recipe.upstream.source_url(upstream_version)

    logger.debug("%s: downloading source and computing its sha256 digest", recipe.name)
    hash_digest = await recipe.upstream.source_sha256_digest(upstream_version)

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

    logger.debug("%s: patching files", recipe.name)
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


async def test_recipe(recipe, folder, version_str, test_lock):
    version_folder_path = os.path.join(recipe.path, folder)

    env = os.environ.copy()
    env["CONAN_HOOK_ERROR_LEVEL"] = "40"

    async with test_lock:
        t0 = time.time()
        logger.info("%s: running test", recipe.name)
        process = await run(
            [
                "conan",
                "create",
                ".",
                f"{recipe.name}/{version_str}@",
            ],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=version_folder_path,
        )
        output, _ = await process.communicate()
        code = await process.wait()
        duration = time.time() - t0

    if code == 0:
        logger.info(
            "%s: test passed in %s",
            recipe.name,
            format_duration(duration),
        )
        return TestStatus(success=True, duration=duration)

    output = output.decode()
    logger.info(output)
    logger.error(
        "%s: test failed in %s",
        recipe.name,
        format_duration(duration),
    )
    return TestStatus(success=False, error=get_test_details(output), duration=duration)


async def _get_most_recent_upstream_version(recipe):
    status = await recipe.status()

    if status.up_to_date():
        raise RecipeNotUpdatable("recipe is up-to-date")

    if not status.update_possible():
        raise RecipeNotUpdatable("update is not possible")

    upstream_version = status.upstream_version
    if upstream_version.unknown:
        raise UpstreamNotSupported("upstream version is unknown")
    return upstream_version


async def _get_user_choice_upstream_version(recipe):
    recipe_versions_fixed = [v.fixed for v in recipe.versions()]
    versions = list(
        sorted(
            v
            for v in await recipe.upstream.versions()
            if v.fixed not in recipe_versions_fixed
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


async def update_one_recipe(
    recipe,
    upstream_version,
    folder,
    run_test,
    push_to,
    force,
    allow_interaction,
    branch_prefix,
    test_lock,
) -> UpdateStatus:
    assert isinstance(recipe, Recipe)

    conan_version = upstream_version.fixed
    branch_name = f"{branch_prefix}{recipe.name}-{conan_version}"
    force_push = force

    if push_to:
        logger.info("%s: pushing", recipe.name)
        branch_remote_owner, branch_remote_repo = await cci_interface.owner_and_repo(
            recipe.path, push_to
        )
    else:
        branch_remote_owner = branch_remote_repo = None

    if await branch_exists(recipe, branch_name):
        if allow_interaction and not force:
            force = yn_question(
                f"Branch '{branch_name}' already exists, overwrite ?", False
            )
        if not force:
            return UpdateStatus(
                updated=False,
                branch_name=branch_name,
                details="branch already exists",
            )
        await remove_branch(recipe, branch_name)

    if await remote_branch_exists(recipe, branch_name, push_to):
        if allow_interaction and not force_push:
            force_push = yn_question(
                f"Remote branch '{push_to}/{branch_name}' already exists, overwrite ?",
                False,
            )
        if not force_push:
            return UpdateStatus(
                updated=False,
                branch_name=branch_name,
                branch_remote_owner=branch_remote_owner,
                branch_remote_repo=branch_remote_repo,
                details="remote branch already exists",
            )

    folder = folder or recipe.folder(recipe.most_recent_version())

    logger.info(
        "%s: adding version %s to folder %s in branch %s from upstream version %s",
        recipe.name,
        conan_version,
        folder,
        branch_name,
        upstream_version,
    )

    async with RecipeInWorktree(recipe) as new_recipe:
        await add_version(new_recipe, folder, conan_version, upstream_version)

        if run_test:
            test_status = await test_recipe(
                new_recipe, folder, conan_version, test_lock
            )
        else:
            test_status = None

        if test_status is None or test_status.success:
            await create_branch_and_commit(
                new_recipe,
                branch_name,
                f"{recipe.name}: add version {conan_version}\n\n"
                "Generated and committed by [Conan Center Bot](https://github.com/qchateau/conan-center-bot)\n"
                "Find more updatable recipes in the [GitHub Pages](https://qchateau.github.io/conan-center-bot/)",
            )

            if push_to:
                logger.info("%s: pushing", recipe.name)
                await push_branch(new_recipe, push_to, branch_name, force_push)

            logger.info(
                "%s: created version %s in branch %s (%s)",
                recipe.name,
                conan_version,
                branch_name,
                "pushed" if push_to else "not pushed",
            )
        else:
            # test failed, we did not push, remote branches
            # either do not exist or are out of date
            branch_remote_owner = branch_remote_repo = None

    return UpdateStatus(
        updated=True,
        test_status=test_status,
        branch_name=branch_name,
        branch_remote_owner=branch_remote_owner,
        branch_remote_repo=branch_remote_repo,
        details=test_status.error if test_status else None,
    )


async def _auto_update_one_recipe(
    recipe_name,
    cci_path,
    branch_prefix,
    push_to,
    test_lock,
):
    recipe = Recipe(cci_path, recipe_name)
    recipe_status = await recipe.status()

    if await recipe_status.prs_opened():
        logger.info("%s: skipped (PR exists)", recipe.name)
        return UpdateStatus(updated=False, details="PR exists")

    try:
        return await update_one_recipe(
            recipe=recipe,
            upstream_version=recipe_status.upstream_version,
            folder=None,
            run_test=True,
            push_to=push_to,
            force=True,
            allow_interaction=False,
            branch_prefix=branch_prefix,
            test_lock=test_lock,
        )
    except Exception:
        logger.error(
            "%s: exception during update:\n%s",
            recipe.name,
            traceback.format_exc(),
        )
        return UpdateStatus(updated=False, details=traceback.format_exc())


async def auto_update_all_recipes(cci_path, branch_prefix, push_to):
    t0 = time.time()
    recipes = get_recipes_list(cci_path)

    # fetch PRs while getting status, it will be cached for later
    status, _ = await asyncio.gather(
        get_status(cci_path, recipes),
        cci_interface.pull_requests(),
    )

    status = [s for s in status if not s.deprecated]
    status = list(sorted(status, key=lambda s: s.name))
    updatable = [s for s in status if s.update_possible()]
    updatable_names = [s.name for s in updatable]

    test_lock = asyncio.Lock()
    update_tasks = [
        asyncio.create_task(
            _auto_update_one_recipe(
                recipe_name,
                cci_path,
                branch_prefix,
                push_to,
                test_lock,
            )
        )
        for recipe_name in updatable_names
    ]

    for i, coro in enumerate(asyncio.as_completed(update_tasks)):
        await coro
        logger.info("-- %s/%s update done --", i + 1, len(update_tasks))

    update_status = dict(zip(updatable_names, [t.result() for t in update_tasks]))

    duration = time.time() - t0

    async def _generate_recipe_update_status(status):
        update = update_status.get(status.name, UpdateStatus(updated=False))
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
                for pr in await status.prs_opened()
            ],
            "updated_branch": {
                "owner": update.branch_remote_owner,
                "repo": update.branch_remote_repo,
                "branch": update.branch_name,
            },
            "update_error": update.details,
            "test_error": update.test_status.error if update.test_status else None,
        }

    status = {
        "date": datetime.datetime.now().isoformat(),
        "duration": duration,
        "version": 1,
        "recipes": [await _generate_recipe_update_status(s) for s in status],
    }
    print(json.dumps(status))
    return 0


async def manual_update_recipes(
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
    test_lock = asyncio.Lock()
    for recipe_name in recipes:
        try:
            recipe = Recipe(cci_path, recipe_name)

            if choose_version:
                upstream_version = await _get_user_choice_upstream_version(recipe)
            else:
                upstream_version = await _get_most_recent_upstream_version(recipe)

            status = await update_one_recipe(
                recipe,
                upstream_version,
                folder,
                run_test,
                push_to,
                force,
                allow_interaction,
                branch_prefix,
                test_lock,
            )
            if not status.updated:
                logger.info("%s: skipped (%s)", recipe_name, status.details)
            elif status.test_ran and not status.test_success:
                logger.error("%s: test failed:\n%s", recipe_name, status.details)
        except (UpdateError, RecipeError) as exc:
            logger.error("%s: %s", recipe_name, str(exc))
            ok = False

    return 0 if ok else 1
