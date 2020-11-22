#!/usr/bin/env python3

import os
import sys
import argparse
import asyncio
import logging

from ccb.recipe import get_recipes_list
from ccb.status import print_status_table
from ccb.update import manual_update_recipes, auto_update_all_recipes
from ccb.github import set_github_token
from ccb.issue import update_status_issue


def bad_command(parser):
    parser.print_usage()
    return 1


def cmd_status(args):
    if not args.recipe:
        args.recipe = get_recipes_list(args.cci)
    else:
        # The user specified a list, show it all
        args.all = True

    return asyncio.run(
        print_status_table(
            cci_path=args.cci,
            recipes=args.recipe,
            print_all=args.all,
        )
    )


def cmd_update(args):
    if not args.recipe:
        args.recipe = get_recipes_list(args.cci)

    return asyncio.run(
        manual_update_recipes(
            cci_path=args.cci,
            recipes=args.recipe,
            choose_version=args.choose_version,
            folder=args.folder,
            run_test=not args.no_test,
            push_to=args.push_to,
            force=args.force,
            allow_interaction=True,
            branch_prefix=args.branch_prefix,
        )
    )


def cmd_update_status_issue(args):
    return asyncio.run(
        update_status_issue(
            update_status_path=args.update_status,
            issue_url_list=args.issue_url,
            no_link_pr=args.no_link_pr,
        )
    )


def cmd_auto_update_recipes(args):
    return asyncio.run(
        auto_update_all_recipes(
            cci_path=args.cci,
            force=args.force,
            push_to=args.push_to,
            branch_prefix=args.branch_prefix,
        )
    )


def configure_logging(args):
    if args.verbose > 0 and args.quiet:
        print("--versbose and --quiet cannot be used together")
        sys.exit(1)
    logging.basicConfig(format="%(message)s")
    logger = logging.getLogger("ccb")
    if args.quiet:
        logger.setLevel(logging.ERROR)
    elif args.verbose == 0:
        logger.setLevel(logging.INFO)
    elif args.verbose >= 1:
        logger.setLevel(logging.DEBUG)


def add_subparser(subparsers, name, function, help_text):
    subparser = subparsers.add_parser(name, help=help_text)

    subparser.add_argument(
        "--verbose", "-v", action="count", default=0, help="Verbosity level"
    )
    subparser.add_argument("--quiet", "-q", action="store_true")
    subparser.add_argument("--github-token", help="Github authentication token")
    subparser.add_argument(
        "--cci",
        help="Path to the conan-center-index repository. Defaults to '../conan-center-index'",
    )

    subparser.set_defaults(func=function)
    return subparser


def main():
    parser = argparse.ArgumentParser()
    parser.set_defaults(
        func=lambda _: bad_command(parser),
        cci=None,
        verbose=False,
        quiet=False,
        github_token=None,
    )
    subparsers = parser.add_subparsers()

    # Status
    parser_status = add_subparser(
        subparsers,
        "status",
        cmd_status,
        help_text="Display the status of recipes",
    )
    parser_status.add_argument(
        "--all",
        "-a",
        action="store_true",
        help="Display all recipes. By default only updatable recipes are displayed.",
    )
    parser_status.add_argument(
        "--recipe",
        nargs="+",
        help="Restrict the recipes status to the ones given as arguments.",
    )

    # Update
    parser_update = add_subparser(
        subparsers,
        "update",
        cmd_update,
        help_text="Auto-update a list of recipes",
    )
    parser_update.add_argument(
        "recipe",
        nargs="*",
        help="List of recipes to update.",
    )
    parser_update.add_argument(
        "--branch-prefix",
        default="ccb-",
        help="Branch name prefix.",
    )
    parser_update.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Overwrite the branch if it exists, force push if the remote branch exists.",
    )
    parser_update.add_argument(
        "--choose-version",
        action="store_true",
        help="Choose which upstream version to use (defaults to the latest)",
    )
    parser_update.add_argument(
        "--folder",
        help="Choose which recipe folder to use (default to the latest)",
    )
    parser_update.add_argument("--push-to", help="Remote name to push new branches to")
    parser_update.add_argument(
        "--no-test", action="store_true", help="Do not test the updated recipe"
    )

    # Auto update recipes
    parser_aur = add_subparser(
        subparsers,
        "auto-update-recipes",
        cmd_auto_update_recipes,
        help_text="Auto update recipes.",
    )
    parser_aur.add_argument(
        "--branch-prefix",
        default="ccb-",
        help="Branch name prefix.",
    )
    parser_aur.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Overwrite the branch if it exists, force push if the remote branch exists.",
    )
    parser_aur.add_argument("--push-to", help="Remote name to push new branches to")

    # Update status issue
    parser_uis = add_subparser(
        subparsers,
        "update-status-issue",
        cmd_update_status_issue,
        help_text="Update the status issue",
    )
    parser_uis.add_argument(
        "update_status", help="Path to the JSON file containing the update status"
    )
    parser_uis.add_argument("issue_url", nargs="*", help="URL of the issues to update")
    parser_uis.add_argument(
        "--no-link-pr",
        action="store_true",
        help="Don't create real link to opened PRs to avoid being referenced by GitHub.",
    )
    args = parser.parse_args()

    if args.github_token:
        set_github_token(args.github_token)

    configure_logging(args)

    if not args.cci:
        args.cci = os.path.realpath(os.path.join("..", "conan-center-index"))
    args.cci = os.path.abspath(args.cci)

    try:
        sys.exit(args.func(args))
    except KeyboardInterrupt:
        sys.exit(1)


if __name__ == "__main__":
    main()
