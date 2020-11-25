import logging
import asyncio

from terminaltables import AsciiTable
from colored import fg, stylize

from .recipe import Recipe

logger = logging.getLogger(__name__)


async def print_status_table(cci_path, recipes_names, print_all):
    recipes = [Recipe(cci_path, name) for name in recipes_names]
    recipes = [r.for_version(r.most_recent_version()) for r in recipes]
    recipes = list(sorted(recipes, key=lambda r: r.name))
    new_upstream_versions = await asyncio.gather(
        *[recipe.upstream().most_recent_version() for recipe in recipes]
    )
    updates = list(zip(recipes, new_upstream_versions))

    table_data = [
        ["Name", "Recipe version", "New version", "Upstream version", "Pending PR"]
    ]
    deprecated = [r for r in recipes if r.deprecated]
    update_possible = [r for r, v in updates if r.version.updatable_to(v)]
    up_to_date = [r for r, v in updates if r.version.up_to_date_with(v)]
    inconsistent_versioning = [r for r, v in updates if r.version.inconsistent_with(v)]
    unsupported_recipe = [r for r in recipes if r.version.unknown]
    unsupported_upstream = [r for r, v in updates if v.unknown]

    for r, v in updates:
        if not r.version.updatable_to(v) and not print_all:
            continue

        if r.deprecated:
            continue

        if r.version.unknown or v.unknown:
            name_color = fg("dark_gray")
        elif r.version.updatable_to(v):
            name_color = fg("dark_orange")
        elif r.version.up_to_date_with(v):
            name_color = fg("green")
        else:
            name_color = fg("red")

        prs = await r.prs_opened_for(v)
        pr_text = str(len(prs))

        rv_color = fg("green") if not r.version.unknown else fg("dark_gray")
        uv_color = fg("green") if not v.unknown else fg("dark_gray")
        pr_color = fg("green") if prs else fg("dark_orange")

        table_data.append(
            [
                stylize(r.name, name_color),
                stylize(r.version, rv_color),
                stylize(v.fixed, uv_color),
                stylize(v, uv_color),
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
