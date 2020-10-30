import os
import sys
import argparse
import logging

from ccb.recipe import get_recipes_list
from ccb.status import print_status_table, print_status_json
from ccb.update import update_recipes

ROOT = os.path.dirname(os.path.realpath(__file__))


def bad_command(args, parser):
    parser.print_usage()
    return 1


def status(args):
    if args.json:
        return print_status_json(
            cci_path=args.cci,
            recipes=args.recipe,
            print_all=args.all,
            jobs=int(args.jobs),
        )
    else:
        return print_status_table(
            cci_path=args.cci,
            recipes=args.recipe,
            print_all=args.all,
            jobs=int(args.jobs),
        )


def update(args):
    return update_recipes(
        cci_path=args.cci,
        recipes=args.recipe,
        run_test=not args.no_test,
        push=args.push,
        force=args.force,
    )


def add_subparser(subparsers, name, function):
    subparser = subparsers.add_parser(name)

    subparser.add_argument("--verbose", "-v", action="count", default=0)
    subparser.add_argument("--cci")

    subparser.set_defaults(func=function)
    return subparser


def main():
    parser = argparse.ArgumentParser()
    parser.set_defaults(func=lambda args: bad_command(args, parser))
    subparsers = parser.add_subparsers()

    parser_status = add_subparser(subparsers, "status", status)
    parser_status.add_argument("--all", "-a", action="store_true")
    parser_status.add_argument("--recipe", nargs="+")
    parser_status.add_argument("--json", action="store_true")
    parser_status.add_argument("--jobs", "-j", default=str(10 * os.cpu_count()))

    parser_update = add_subparser(subparsers, "update", update)
    parser_update.add_argument("recipe", nargs="+")
    parser_update.add_argument("--force", action="store_true")
    parser_update.add_argument("--push", action="store_true")
    parser_update.add_argument("--no-test", action="store_true")

    args = parser.parse_args()

    logging.basicConfig(format="%(message)s")
    logger = logging.getLogger("ccb")
    if args.verbose == 0:
        logger.setLevel(logging.ERROR)
    elif args.verbose == 1:
        logger.setLevel(logging.INFO)
    elif args.verbose > 1:
        logger.setLevel(logging.DEBUG)

    if not args.cci:
        args.cci = os.path.join(ROOT, "..", "conan-center-index")

    args.cci = os.path.abspath(args.cci)
    if not os.path.exists(args.cci):
        print(f"CCI repository not found at {args.cci}")
        sys.exit(1)

    if not args.recipe:
        args.recipe = get_recipes_list(args.cci)

    try:
        sys.exit(args.func(args))
    except KeyboardInterrupt:
        sys.exit(1)


if __name__ == "__main__":
    main()
