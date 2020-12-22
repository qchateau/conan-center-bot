import os
import re
import copy
import time
import typing
import logging
import subprocess

from ..recipe import VersionedRecipe
from ..yaml import yaml, DoubleQuotes
from ..version import Version
from ..cci import cci_interface
from ..utils import format_duration, LockStorage
from ..subprocess import run
from ..git import (
    RecipeInWorktree,
    push_branch,
    create_branch_and_commit,
    count_commits_matching,
)


logger = logging.getLogger(__name__)
test_lock = LockStorage()

RE_HOOK_ERROR = re.compile(r"^\[HOOK.*\].*:\s*ERROR:\s*(.*)$", re.M)
RE_TEST_ERRORS = [
    re.compile(r"^ERROR:.*(Error in.*)", re.M | re.S),
    re.compile(r"^ERROR:.*(Invalid configuration.*)", re.M | re.S),
    re.compile(r"^ERROR:\s*(.*)", re.M | re.S),
]
RE_ALREADY_PATCHED = re.compile(r"WARN:\s*(.*):\s*already patched", re.M)
RE_CREATE_ERRORS = [RE_ALREADY_PATCHED]

RE_CMAKELISTS_VERSION = re.compile(
    r"(cmake_minimum_required\s*\(\s*VERSION\s*)([0-9\.]+)(\s*\))", re.I
)


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
    matches = list(RE_HOOK_ERROR.finditer(output))
    if matches:
        errors = [match.group(1) for match in matches]
        return "Hook validation failed:\n" + "\n".join(errors)

    for regex in RE_TEST_ERRORS:
        match = regex.search(output)
        if match:
            return match.group(1)

    matches = list(RE_ALREADY_PATCHED.finditer(output))
    if matches:
        patches = {m.group(1) for m in matches}
        return "Patch already applied:\n" + "\n".join(patches)

    return "no details"


async def count_ccb_commits(cci_path):
    return await count_commits_matching(
        cci_path, r"https:\/\/github\.com\/qchateau\/conan-center-bot"
    )


async def patch_cmakelists_version(recipe):
    if not os.path.exists(recipe.cmakelists_path):
        logger.warning("%s: CMakeLists.txt not found", recipe.name)
        return

    with open(recipe.cmakelists_path) as f:
        content = f.read()

    match = RE_CMAKELISTS_VERSION.search(content)
    if not match:
        logger.warning("%s: CMake minimum version not found", recipe.name)
        return

    version = Version(match.group(2))
    if version >= Version("3.1"):
        return

    logger.info("%s: updating CMake minimum version", recipe.name)
    content = RE_CMAKELISTS_VERSION.sub(r"\g<1>3.1\g<3>", content)

    with open(recipe.cmakelists_path, "w") as f:
        f.write(content)


async def add_version(recipe, upstream_version):
    conan_version = upstream_version.fixed
    url = recipe.upstream().source_url(upstream_version)

    logger.debug("%s: downloading source and computing its sha256 digest", recipe.name)
    hash_digest = await recipe.upstream().source_sha256_digest(upstream_version)

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
    config["versions"][conan_version]["folder"] = recipe.folder

    conandata = recipe.conandata()
    smart_insert(conandata["sources"], DoubleQuotes(conan_version), {})
    conandata["sources"][conan_version]["url"] = DoubleQuotes(url)
    conandata["sources"][conan_version]["sha256"] = DoubleQuotes(hash_digest)

    most_recent_patches = conandata.get("patches", {}).get(recipe.version.fixed)
    if most_recent_patches:
        smart_insert(
            conandata["patches"],
            DoubleQuotes(conan_version),
            copy.deepcopy(most_recent_patches),
        )

    with open(recipe.config_path, "w") as fil:
        yaml.dump(config, fil)

    with open(recipe.conandata_path, "w") as fil:
        yaml.dump(conandata, fil)

    return conan_version


async def test_recipe(recipe, version_str):
    env = os.environ.copy()
    env["CONAN_HOOK_ERROR_LEVEL"] = "40"

    async with test_lock.get():
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
            cwd=recipe.folder_path,
        )
        output, _ = await process.communicate()
        output = output.decode()
        code = await process.wait()
        duration = time.time() - t0

    if code != 0:
        logger.info(output)
        logger.error(
            "%s: test failed in %s",
            recipe.name,
            format_duration(duration),
        )
        return TestStatus(
            success=False, duration=duration, error=get_test_details(output)
        )

    for regex in RE_CREATE_ERRORS:
        if regex.search(output):
            return TestStatus(
                success=False, duration=duration, error=get_test_details(output)
            )

    logger.info(
        "%s: test passed in %s",
        recipe.name,
        format_duration(duration),
    )
    return TestStatus(success=True, duration=duration)


async def update_one_recipe(
    recipe,
    new_upstream_version,
    run_test,
    push_to,
    force_push,
    branch_name,
) -> UpdateStatus:
    assert isinstance(recipe, VersionedRecipe)

    logger.info(
        "%s: adding upstream version %s based on %s in branch %s",
        recipe.name,
        new_upstream_version,
        recipe.version,
        branch_name,
    )

    async with RecipeInWorktree(recipe) as new_recipe:
        await patch_cmakelists_version(new_recipe)
        conan_version = await add_version(new_recipe, new_upstream_version)

        test_status = None
        if run_test:
            test_status = await test_recipe(new_recipe, conan_version)

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
