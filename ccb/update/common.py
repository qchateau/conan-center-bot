import os
import re
import copy
import time
import typing
import logging
import subprocess

from ..recipe import Recipe
from ..yaml import yaml, DoubleQuotes
from ..version import Version
from ..cci import cci_interface
from ..utils import format_duration
from ..subprocess import run
from ..git import (
    RecipeInWorktree,
    push_branch,
    create_branch_and_commit,
)


logger = logging.getLogger(__name__)

RE_TEST_ERRORS = [
    re.compile(r"^\[HOOK.*\].*:\s*ERROR:\s*(.*)$", re.M),
    re.compile(r"^ERROR:.*(Error in.*)", re.M | re.S),
    re.compile(r"^ERROR:.*(Invalid configuration.*)", re.M | re.S),
    re.compile(r"^ERROR:\s*(.*)", re.M | re.S),
]


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


def get_test_details(output):
    for regex in RE_TEST_ERRORS:
        errors = [match.group(1) for match in regex.finditer(output)]
        if errors:
            return "\n".join(errors)
    return "no details"


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


async def update_one_recipe(
    recipe,
    upstream_version,
    folder,
    run_test,
    push_to,
    force_push,
    branch_name,
    test_lock,
) -> UpdateStatus:
    assert isinstance(recipe, Recipe)

    conan_version = upstream_version.fixed
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

        test_status = None
        if run_test:
            test_status = await test_recipe(
                new_recipe, folder, conan_version, test_lock
            )

            if not test_status.success:
                return UpdateStatus(
                    updated=False,
                    test_status=test_status,
                    branch_name=branch_name,
                    details=test_status.error,
                )

        await create_branch_and_commit(
            new_recipe,
            branch_name,
            f"{recipe.name}: add version {conan_version}\n\n"
            "Generated and committed by [Conan Center Bot](https://github.com/qchateau/conan-center-bot)\n"
            "Find more updatable recipes in the [GitHub Pages](https://qchateau.github.io/conan-center-bot/)",
        )

        if push_to:
            logger.info("%s: pushing", recipe.name)
            owner, repo = await cci_interface.owner_and_repo(recipe.path, push_to)
            await push_branch(new_recipe, push_to, branch_name, force_push)
        else:
            owner = repo = None

    logger.info(
        "%s: created version %s in branch %s (%s)",
        recipe.name,
        conan_version,
        branch_name,
        "pushed" if push_to else "not pushed",
    )

    return UpdateStatus(
        updated=True,
        test_status=test_status,
        branch_name=branch_name,
        branch_remote_owner=owner,
        branch_remote_repo=repo,
    )
