import logging

from ..recipe import Recipe, RecipeError
from ..utils import yn_question
from ..git import (
    branch_exists,
    remote_branch_exists,
    remove_branch,
)
from .common import update_one_recipe


logger = logging.getLogger(__name__)


class UpdateError(RuntimeError):
    pass


class UpstreamNotSupported(UpdateError):
    pass


class RecipeNotUpdatable(UpdateError):
    pass


async def get_most_recent_upstream_version(recipe):
    status = await recipe.status()

    if status.up_to_date():
        raise RecipeNotUpdatable("recipe is up-to-date")

    if not status.update_possible():
        raise RecipeNotUpdatable("update is not possible")

    upstream_version = status.upstream_version
    if upstream_version.unknown:
        raise UpstreamNotSupported("upstream version is unknown")
    return upstream_version


async def get_user_choice_upstream_version(recipe):
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


async def manual_update_one_recipe(
    cci_path,
    recipe_name,
    choose_version,
    folder,
    run_test,
    push_to,
    force,
    branch_prefix,
):
    recipe = Recipe(cci_path, recipe_name)

    if choose_version:
        upstream_version = await get_user_choice_upstream_version(recipe)
    else:
        upstream_version = await get_most_recent_upstream_version(recipe)

    conan_version = upstream_version.fixed
    branch_name = f"{branch_prefix}{recipe.name}-{conan_version}"
    if await branch_exists(recipe, branch_name):
        if not force:
            force = yn_question(
                f"Branch '{branch_name}' already exists, overwrite ?", False
            )
        if not force:
            return
        await remove_branch(recipe, branch_name)

    force_push = force
    if push_to and await remote_branch_exists(recipe, branch_name, push_to):
        if not force_push:
            force_push = yn_question(
                f"Remote branch '{push_to}/{branch_name}' already exists, overwrite ?",
                False,
            )
        if not force_push:
            return

    status = await update_one_recipe(
        recipe=recipe,
        upstream_version=upstream_version,
        folder=folder,
        run_test=run_test,
        push_to=push_to,
        force_push=force_push,
        branch_name=branch_name,
    )

    if not status.updated:
        logger.info("%s: skipped (%s)", recipe_name, status.details)
    elif status.test_ran and not status.test_success:
        logger.error("%s: test failed:\n%s", recipe_name, status.details)


async def manual_update_recipes(
    cci_path,
    recipes,
    choose_version,
    folder,
    run_test,
    push_to,
    force,
    branch_prefix,
):
    ok = True
    for recipe_name in recipes:
        try:
            await manual_update_one_recipe(
                cci_path=cci_path,
                recipe_name=recipe_name,
                choose_version=choose_version,
                folder=folder,
                run_test=run_test,
                push_to=push_to,
                force=force,
                branch_prefix=branch_prefix,
            )
        except (UpdateError, RecipeError) as exc:
            logger.error("%s: %s", recipe_name, str(exc))
            ok = False

    return 0 if ok else 1
