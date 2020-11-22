import logging
import asyncio

from terminaltables import AsciiTable
from colored import fg, stylize

from .recipe import Recipe
from . import __version__

logger = logging.getLogger(__name__)


async def get_status(cci_path, recipes):
    logger.info("Parsing %s recipes...", len(recipes))

    return await asyncio.gather(
        *[Recipe(cci_path, recipe).status() for recipe in recipes]
    )


async def print_status_table(cci_path, recipes, print_all):
    status = await get_status(cci_path, recipes)
    table_data = [
        ["Name", "Recipe version", "New version", "Upstream version", "Pending PR"]
    ]
    deprecated = [s for s in status if s.deprecated]
    update_possible = [s for s in status if s.update_possible()]
    up_to_date = [s for s in status if s.up_to_date()]
    inconsistent_versioning = [s for s in status if s.inconsistent_versioning()]
    unsupported_recipe = [s for s in status if s.recipe_version.unknown]
    unsupported_upstream = [s for s in status if s.upstream_version.unknown]

    for s in sorted(status, key=lambda r: r.name):
        if not s.update_possible() and not print_all:
            continue

        if s.deprecated:
            continue

        if s.recipe_version.unknown or s.upstream_version.unknown:
            name_color = fg("dark_gray")
        elif s.update_possible():
            name_color = fg("dark_orange")
        elif s.up_to_date():
            name_color = fg("green")
        else:
            name_color = fg("red")

        prs = await s.prs_opened()
        pr_text = str(len(prs))

        rv_color = fg("green") if not s.recipe_version.unknown else fg("dark_gray")
        uv_color = fg("green") if not s.upstream_version.unknown else fg("dark_gray")
        pr_color = fg("green") if prs else fg("dark_orange")

        table_data.append(
            [
                stylize(s.name, name_color),
                stylize(s.recipe_version, rv_color),
                stylize(s.upstream_version.fixed, uv_color),
                stylize(s.upstream_version, uv_color),
                stylize(pr_text, pr_color),
            ]
        )

    table = AsciiTable(table_data)

    def print_recipe_type(name, recipes, print_homepage=False):
        if not recipes:
            return

        print(f"{len(recipes)} {name}")
        if print_all:
            for r in recipes:
                print(
                    f" * {r.name}"
                    + (f" ({r.homepage})" if print_homepage and r.homepage else "")
                )
            print()

    print_recipe_type("deprecated recipes", deprecated)
    print_recipe_type("updatable recipes", update_possible)
    print_recipe_type("up-to-date recipes", up_to_date)
    print_recipe_type("inconsistent recipes", inconsistent_versioning)
    print_recipe_type("unsupported recipes", unsupported_recipe)
    print_recipe_type("unsupported upstream", unsupported_upstream, print_homepage=True)
    print()
    print(table.table)
    return 0
