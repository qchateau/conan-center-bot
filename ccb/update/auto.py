import os
import json
import time
import asyncio
import logging
import datetime
import traceback

from .common import update_one_recipe, UpdateStatus
from ..recipe import Recipe, get_recipes_list
from ..cci import cci_interface
from ..status import get_status


logger = logging.getLogger(__name__)


async def auto_update_one_recipe(
    recipe_name,
    cci_path,
    branch_prefix,
    push_to,
    test_lock,
):
    recipe = Recipe(cci_path, recipe_name)
    recipe_status = await recipe.status()
    upstream_version = recipe_status.upstream_version
    branch_name = f"{branch_prefix}{recipe.name}-{upstream_version.fixed}"

    if await recipe_status.prs_opened():
        logger.info("%s: skipped (PR exists)", recipe.name)
        return UpdateStatus(updated=False, details="PR exists")

    try:
        return await update_one_recipe(
            recipe=recipe,
            upstream_version=upstream_version,
            folder=None,
            run_test=True,
            push_to=push_to,
            force_push=True,
            branch_name=branch_name,
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
            auto_update_one_recipe(
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
        "github_action_run_id": os.environ.get("GITHUB_RUN_ID", None),
    }
    print(json.dumps(status))
    return 0
