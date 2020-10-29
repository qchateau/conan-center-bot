import os
import re
import sys
import argparse
import inspect
import hashlib
import subprocess
import importlib.util
from multiprocessing import Pool

import yaml
import requests

from ccb.config import set_github_token
from ccb.recipe import Recipe, get_recipes_list
from ccb.upstream_project import get_upstream_project
from ccb.exceptions import (
    UnsupportedRecipe,
    UnsupportedUpstreamProject,
    VersionAlreadyExists,
    TestFailed,
)
from ccb.worktree import RecipeInWorktree


def add_version(recipe, args):
    upstream = get_upstream_project(recipe)
    if not upstream.versions:
        raise UnsupportedUpstreamProject("No versions in upstream project")

    version = upstream.most_recent_version

    if recipe.version_exists(version):
        raise VersionAlreadyExists("Version already exists in CCI")

    branch_name = f"{recipe.name}-{version.fixed}"
    if (
        subprocess.call(
            ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch_name}"],
            cwd=recipe.path,
        )
        == 0
    ):
        if args.force:
            subprocess.check_output(
                ["git", "branch", "-q", "-D", branch_name], cwd=recipe.path
            )
        else:
            raise VersionAlreadyExists("A branch already exists for this version")

    if (
        not args.force
        and subprocess.call(
            [
                "git",
                "show-ref",
                "--verify",
                "--quiet",
                f"refs/remotes/{args.remote}/{branch_name}",
            ],
            cwd=recipe.path,
        )
        == 0
    ):
        raise VersionAlreadyExists("A remote branch already exists for this version")

    url = upstream.tarball_url(version)
    hash_digest = upstream.tarball_sha256_digest(version)
    folder = recipe.versions_folders[recipe.most_recent_version]

    with RecipeInWorktree(recipe) as new_recipe:
        new_recipe.add_version(folder, version, url, hash_digest)

        if args.test:
            try:
                new_recipe.test(version)
            except subprocess.CalledProcessError as exc:
                raise TestFailed(exc.output.decode())

        subprocess.check_call(
            ["git", "checkout", "-q", "-b", branch_name], cwd=new_recipe.path
        )
        subprocess.check_call(
            [
                "git",
                "commit",
                "-q",
                "-a",
                "-m",
                f"{recipe.name}: add version {version.fixed}",
            ],
            cwd=new_recipe.path,
        )

        if args.push:
            subprocess.check_output(
                ["git", "push", "-q", "--set-upstream"]
                + (["-f"] if args.force else [])
                + [args.remote, branch_name],
                cwd=new_recipe.path,
            )

    return version, branch_name


def process_recipe(recipe_name, args):
    print(f"{recipe_name}...\r", end="")
    sys.stdout.flush()
    try:
        recipe = Recipe(args.conan_center_index_path, recipe_name)
        version, branch_name = add_version(recipe, args)
        print(f"{recipe_name:20}: added {version.fixed} in branch {branch_name}")
    except UnsupportedRecipe as e:
        print(f"{recipe_name:20}: unsupported recipe ({str(e)[:50]})")
    except UnsupportedUpstreamProject as e:
        print(f"{recipe_name:20}: unsupported project ({str(e)[:50]})")
    except TestFailed as e:
        print(f"{recipe_name:20}: skipped ({str(e)[:50]})")
        print()
        print()
        print("=" * 80)
        print(e.output)
        print("=" * 80)
        print()
        print()
    except VersionAlreadyExists as e:
        print(f"{recipe_name:20}: skipped ({str(e)[:50]})")
    except Exception as e:
        print(f"{recipe_name:20}: error ({repr(e)[:50]})")
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("conan_center_index_path")
    parser.add_argument("--recipe", nargs="*")
    parser.add_argument("--github-token")
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--force", "-f", action="store_true")
    parser.add_argument("--processes", default=os.cpu_count())
    args = parser.parse_args()

    args.conan_center_index_path = os.path.abspath(args.conan_center_index_path)

    if args.github_token:
        set_github_token(args.github_token)

    if args.recipe:
        recipes = args.recipe
    else:
        recipes = get_recipes_list(args.conan_center_index_path)

    print(f"Using {len(recipes)} recipes")

    with Pool(int(args.processes)) as p:
        results = [
            p.apply_async(process_recipe, args=(recipe, args)) for recipe in recipes
        ]
        for r in results:
            r.get()


if __name__ == "__main__":
    main()
