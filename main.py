import os
import sys
import argparse
import logging

from ccb.recipe import get_recipes_list
from ccb.status import print_status_table, print_status_json

ROOT = os.path.dirname(os.path.realpath(__file__))


def bad_command(args, parser):
    parser.print_usage()
    return 1


def main_status(args):
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


def add_subparser(subparsers, name, function):
    subparser = subparsers.add_parser(name)

    subparser.add_argument("--versbose", "-v", action="store_true")
    subparser.add_argument("--cci")
    subparser.add_argument("--recipe", nargs="+")

    subparser.set_defaults(func=function)
    return subparser


def main():
    parser = argparse.ArgumentParser()
    parser.set_defaults(func=lambda args: bad_command(args, parser))
    subparsers = parser.add_subparsers()

    parser_status = add_subparser(subparsers, "status", main_status)
    parser_status.add_argument("--all", "-a", action="store_true")
    parser_status.add_argument("--json", action="store_true")
    parser_status.add_argument("--jobs", "-j", default=str(10 * os.cpu_count()))

    args = parser.parse_args()

    if args.versbose:
        logging.basicConfig()
        logger = logging.getLogger("ccb")
        logger.setLevel(logging.DEBUG)

    if not args.cci:
        args.cci = os.path.join(ROOT, "..", "conan-center-index")

    args.cci = os.path.abspath(args.cci)
    if not os.path.exists(args.cci):
        print(f"CCI repository not found at {args.cci}")
        sys.exit(1)

    if not args.recipe:
        args.recipe = get_recipes_list(args.cci)

    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
