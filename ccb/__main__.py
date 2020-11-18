#!/usr/bin/env python3

import os
import sys
import argparse
import logging

from ccb.recipe import get_recipes_list
from ccb.status import print_status_table
from ccb.update import update_recipes
from ccb.github import set_github_token
from ccb.actions import update_status_issue


def bad_command(parser):
    parser.print_usage()
    return 1


def cmd_status(args):
    return print_status_table(
        cci_path=args.cci,
        recipes=args.recipe,
        print_all=args.all,
        jobs=int(args.jobs),
    )


def cmd_update(args):
    return update_recipes(
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


def cmd_update_status_issue(args):
    return update_status_issue(
        cci_path=args.cci,
        issue_url_list=args.issue_url,
        force=args.force,
        push_to=args.push_to,
        status_jobs=int(args.jobs),
        branch_prefix=args.branch_prefix,
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
    subparser.add_argument(
        "--cci",
        help="Path to the conan-center-index repository. Defaults to '../conan-center-index'",
    )
    subparser.add_argument("--github-token", help="Github authentication token")

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
        subparsers, "status", cmd_status, help_text="Display the status of recipes"
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
    parser_status.add_argument(
        "--jobs",
        "-j",
        default=str(10 * os.cpu_count()),
        help="Number of parallel processes.",
    )

    # Update
    parser_update = add_subparser(
        subparsers, "update", cmd_update, help_text="Auto-update a list of recipes"
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

    # Update status issue
    parser_uis = add_subparser(
        subparsers,
        "update-status-issue",
        cmd_update_status_issue,
        help_text="Update the status issue",
    )
    parser_uis.add_argument("issue_url", nargs="*", help="URL of the issues to update")
    parser_uis.add_argument(
        "--branch-prefix",
        default="ccb-",
        help="Branch name prefix.",
    )
    parser_uis.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Overwrite the branch if it exists, force push if the remote branch exists.",
    )
    parser_uis.add_argument("--push-to", help="Remote name to push new branches to")
    parser_uis.add_argument(
        "--jobs",
        "-j",
        default=str(10 * os.cpu_count()),
        help="Number of parallel processes during status fetch.",
    )

    args = parser.parse_args()

    if args.github_token:
        set_github_token(args.github_token)

    configure_logging(args)

    if not args.cci:
        args.cci = os.path.realpath(os.path.join("..", "conan-center-index"))

    args.cci = os.path.abspath(args.cci)
    if not os.path.exists(args.cci):
        print(f"CCI repository not found at {args.cci}")
        sys.exit(1)

    if not hasattr(args, "recipe") or not args.recipe:
        args.recipe = get_recipes_list(args.cci)
    else:
        # The user specified a list, show it all
        args.all = True

    try:
        sys.exit(args.func(args))
    except KeyboardInterrupt:
        sys.exit(1)


if __name__ == "__main__":
    main()
