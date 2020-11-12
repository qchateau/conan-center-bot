# Conan Center Bot

This is a library to help update recipes in conan-center-index.

The library will scan a conan-center-index repository as well as
all recipes's upstream to try to find which recipes can be updated.

It can then either generates the list of updatable recipes, or
automatically update a recipe to the latest upstream version.

This library is used to keep https://github.com/conan-io/conan-center-index/issues/3470
and https://github.com/qchateau/conan-center-bot/issues/1 up to date.

## How to use it

### Install from pypi

```
pip3 install conan-center-bot
```

### Install from source

```
pip3 install .
```

### Run

Use the help, it will be more up to date than this README !

```
conan-center-bot -h
```

### Get the status of recipes in CCI

```
usage: conan-center-bot status [-h] [--verbose] [--quiet] [--cci CCI] [--github-token GITHUB_TOKEN] [--all] [--recipe RECIPE [RECIPE ...]] [--jobs JOBS]

optional arguments:
  -h, --help            show this help message and exit
  --verbose, -v         Verbosity level
  --quiet, -q
  --cci CCI             Path to the conan-center-index repository. Defaults to '../conan-center-index'
  --github-token GITHUB_TOKEN
                        Github authentication token
  --all, -a             Display all recipes. By default only updatable recipes are displayed.
  --recipe RECIPE [RECIPE ...]
                        Restrict the recipes status to the ones given as arguments.
  --jobs JOBS, -j JOBS  Number of parallel processes.
```

### Update a recipe

```
usage: conan-center-bot update [-h] [--verbose] [--quiet] [--cci CCI] [--github-token GITHUB_TOKEN] [--force] [--choose-version] [--folder FOLDER] [--push] [--no-test] [recipe [recipe ...]]

positional arguments:
  recipe                List of recipes to update.

optional arguments:
  -h, --help            show this help message and exit
  --verbose, -v         Verbosity level
  --quiet, -q
  --cci CCI             Path to the conan-center-index repository. Defaults to '../conan-center-index'
  --github-token GITHUB_TOKEN
                        Github authentication token
  --force, -f           Overwrite the branch if it exists, force push if the remote branch exists.
  --choose-version      Choose which upstream version to use (defaults to the latest)
  --folder FOLDER       Choose which recipe folder to use (default to the latest)
  --push                Push the new branch to origin
  --no-test             Do not test the updated recipe
```

To auto-update and test a recipe, run

```bash
conan-center-bot update <recipe-name> --push --cci <path-to-cci>
```

After you ran the script:

- Verify and maybe tweak the diff in the new branch
- Open a PR on CCI

## Limitations

- Only projects on GitHub are supported.
- Some versioning patterns are too specific to be supported.
- Recipes require a config.yml file.
