import os
import json
import time
import typing
import asyncio
import logging
import datetime
import traceback

from .common import update_one_recipe, UpdateStatus
from ..version import Version
from ..recipe import Recipe, VersionedRecipe, get_recipes_list
from ..git import branch_exists, remove_branch
from ..utils import format_duration


logger = logging.getLogger(__name__)


class RecipeInfo(typing.NamedTuple):
    recipe: VersionedRecipe
    new_upstream_version: Version
    update_task: typing.Optional[asyncio.Task]
    details: typing.Optional[str]


async def auto_update_one_recipe(
    recipe,
    new_upstream_version,
    branch_prefix,
    push_to,
):
    assert isinstance(recipe, VersionedRecipe)
    branch_name = f"{branch_prefix}{recipe.name}-{new_upstream_version.fixed}"

    try:
        if await recipe.prs_opened_for(new_upstream_version):
            logger.info("%s: skipped (PR exists)", recipe.name)
            return UpdateStatus(updated=False, details="PR exists")

        if await branch_exists(recipe, branch_name):
            await remove_branch(recipe, branch_name)

        return await update_one_recipe(
            recipe=recipe,
            new_upstream_version=new_upstream_version,
            run_test=True,
            push_to=push_to,
            force_push=True,
            branch_name=branch_name,
        )
    except Exception:
        logger.error(
            "%s: exception during update:\n%s",
            recipe.name,
            traceback.format_exc(),
        )
        return UpdateStatus(updated=False, details=traceback.format_exc())


def format_optional_date(maybe_date):
    if not maybe_date:
        return None
    return maybe_date.isoformat()


async def generate_recipe_update_status(info: RecipeInfo):
    recipe = info.recipe
    recipe_upstream_version = await recipe.upstream_version()
    new_upstream_version = info.new_upstream_version
    update = info.update_task.result() if info.update_task else UpdateStatus(False)
    return {
        "name": recipe.name,
        "homepage": recipe.homepage,
        "current": {
            "version": recipe.version.original,
            "tag": recipe_upstream_version.original,
            "date": format_optional_date(recipe_upstream_version.meta.date),
            "commit_count": recipe_upstream_version.meta.commit_count,
        },
        "new": {
            "version": new_upstream_version.fixed,
            "tag": new_upstream_version.original,
            "date": format_optional_date(new_upstream_version.meta.date),
            "commit_count": new_upstream_version.meta.commit_count,
        },
        "deprecated": recipe.deprecated,
        "inconsistent_versioning": recipe.version.inconsistent_with(
            new_upstream_version
        ),
        "updatable": recipe.version.updatable_to(new_upstream_version),
        "up_to_date": recipe.version.up_to_date_with(new_upstream_version),
        "supported": (
            recipe.supported
            and not recipe.version.unknown
            and not new_upstream_version.unknown
        ),
        "prs_opened": [
            {
                "number": pr.number,
                "url": pr.url,
            }
            for pr in await recipe.prs_opened_for(new_upstream_version)
        ],
        "updated_branch": {
            "owner": update.branch_remote_owner,
            "repo": update.branch_remote_repo,
            "branch": update.branch_name,
        },
        "details": update.details or info.details,
        "test_error": update.test_status.error if update.test_status else None,
    }


async def recipe_info_details(recipe):
    if not recipe.supported:
        return "Unsupported recipe"
    if (await recipe.upstream().most_recent_version()).unknown:
        return "Unsupported upstream"
    return None


async def auto_update_all_recipes(cci_path, branch_prefix, push_to):
    t0 = time.time()
    recipes = [Recipe(cci_path, name) for name in get_recipes_list(cci_path)]
    recipes = list(sorted(recipes, key=lambda r: r.name))

    logger.info("parsing upstreams for %s recipes", len(recipes))
    recipes = [recipe.for_version(recipe.most_recent_version()) for recipe in recipes]
    parsing_tasks = [
        asyncio.create_task(recipe.upstream().most_recent_version())
        for recipe in recipes
    ]

    for i, coro in enumerate(asyncio.as_completed(parsing_tasks)):
        await coro
        logger.info("-- %s/%s parsing done --", i + 1, len(parsing_tasks))

    new_upstream_versions = [t.result() for t in parsing_tasks]
    logger.info(
        "parsed %s upstreams in %s", len(recipes), format_duration(time.time() - t0)
    )
    infos = [
        RecipeInfo(
            recipe=r,
            new_upstream_version=v,
            update_task=asyncio.create_task(
                auto_update_one_recipe(
                    r,
                    v,
                    branch_prefix,
                    push_to,
                )
            )
            if not r.deprecated and r.version.updatable_to(v)
            else None,
            details=await recipe_info_details(r),
        )
        for (r, v) in zip(recipes, new_upstream_versions)
    ]

    update_tasks = [info.update_task for info in infos if info.update_task]
    for i, coro in enumerate(asyncio.as_completed(update_tasks)):
        await coro
        logger.info("-- %s/%s update done --", i + 1, len(update_tasks))

    duration = time.time() - t0

    status = {
        "date": datetime.datetime.now().isoformat(),
        "duration": duration,
        "version": 3,
        "recipes": await asyncio.gather(
            *[generate_recipe_update_status(info) for info in infos]
        ),
        "github_action_run_id": os.environ.get("GITHUB_RUN_ID", None),
    }
    print(json.dumps(status))
    return 0
