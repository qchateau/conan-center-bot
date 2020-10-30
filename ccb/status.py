import json
import logging
import typing
from multiprocessing import Pool
from terminaltables import AsciiTable
from colored import fg, stylize

from .recipe import get_recipes_list, Recipe
from .exceptions import RecipeError
from .version import Version

logger = logging.getLogger(__name__)


class Status(typing.NamedTuple):
    name: str
    recipe_version: Version
    upstream_version: Version

    def update_possible(self):
        return (
            not self.upstream_version.unknown
            and not self.recipe_version.unknown
            and self.upstream_version > self.recipe_version
        )


def status_one_recipe(cci_path, recipe_name):
    try:
        recipe = Recipe(cci_path, recipe_name)
        recipe_version = recipe.most_recent_version
        recipe_upstream_version = recipe.upstream.most_recent_version
    except RecipeError as exc:
        logger.warn("%s: could not find version: %s", recipe_name, exc)
        recipe_version = Version()
        recipe_upstream_version = Version()

    return Status(recipe_name, recipe_version, recipe_upstream_version)


def get_status(cci_path, recipes, jobs):
    logger.info(f"Parsing {len(recipes)} recipes")

    with Pool(jobs) as p:
        status_futures = [
            p.apply_async(status_one_recipe, args=(cci_path, recipe))
            for recipe in recipes
        ]
        return [f.get() for f in status_futures]


def print_status_json(cci_path, recipes, print_all, jobs):
    status = get_status(cci_path, recipes, jobs)
    data = list()
    for s in status:
        if not s.update_possible() and not print_all:
            continue
        data.append(
            {
                "name": s.name,
                "recipe_version": str(s.recipe_version),
                "upstream_version": str(s.upstream_version),
                "update_possible": s.update_possible(),
            }
        )
    print(json.dumps(data))
    return 0


def print_status_table(cci_path, recipes, print_all, jobs):
    status = get_status(cci_path, recipes, jobs)
    table_data = [["Name", "Recipe version", "Upstream version"]]
    for s in status:
        if s.recipe_version.unknown or s.upstream_version.unknown:
            name_color = fg("red")
        elif s.update_possible():
            name_color = fg("dark_orange")
        else:
            name_color = fg("green")

        if not s.update_possible() and not print_all:
            continue

        rv_color = fg("green") if not s.recipe_version.unknown else fg("red")
        uv_color = fg("green") if not s.upstream_version.unknown else fg("red")

        table_data.append(
            [
                stylize(s.name, name_color),
                stylize(s.recipe_version, rv_color),
                stylize(s.upstream_version, uv_color),
            ]
        )

    table = AsciiTable(table_data)
    print(table.table)
    return 0