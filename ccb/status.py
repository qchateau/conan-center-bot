import json
import logging
from multiprocessing import Pool
from terminaltables import AsciiTable
from colored import fg, stylize

from .recipe import get_recipes_list, Recipe
from .version import Version

logger = logging.getLogger(__name__)


def status_one_recipe(cci_path, recipe_name):
    return Recipe(cci_path, recipe_name).status()


def get_status(cci_path, recipes, jobs):
    logger.info(f"Parsing {len(recipes)} recipes...")

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