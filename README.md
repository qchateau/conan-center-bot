# Conan Center Bot

This is a library to help update recipes in conan-center-index.

The library will scan a conan-center-index repository as well as
all recipes's upstream to try to find which recipes can be updated.

It can then either generates the list of updatable recipes, or
automatically update a recipe to the latest upstream version.

This library is used to keep https://github.com/conan-io/conan-center-index/issues/3470
and https://github.com/qchateau/conan-center-bot/issues/1 up to date.

## How to use it

Use the help, it will be more up to date than this README !

```
python -m ccb -h
```

### Update a recipe

```
usage: main.py update [-h] [--verbose] [--cci CCI] [--force] [--push] [--no-test] recipe [recipe ...]

positional arguments:
  recipe         List of recipes to update.

optional arguments:
  -h, --help     show this help message and exit
  --verbose, -v  Verbosity level
  --cci CCI      Path to the conan-center-index repository. Defaults to '../conan-center-index'
  --force        Overwrite the branch if it exists, force push if the remote branch exists.
  --push         Push the new branch to origin
  --no-test      Do not test the updated recipe
```

To auto-update and test a recipe, run

```bash
python3 main.py update <recipe-name> --push --cci <path-to-cci>
```

After you ran the script:

- Verify and maybe tweak the diff in the new branch
- Open a PR on CCI

## Limitations

- Only projects on GitHub are supported.
- Some versioning patterns are too specific to be supported.
- Recipes require a config.yml file.
