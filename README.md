# conan-center-bot

This is a script to help update recipes in conan-center-index.
Currently is only supports updating recipes that use GitHub.

## How does it work

```
usage: main.py [-h] {status,update} ...

positional arguments:
  {status,update}
    status         Display the status of recipes
    update         Auto-update a list of recipes

optional arguments:
  -h, --help       show this help message and exit
```

The command will try to locate the most recent version in CCI, and the most recent version in GitHub.

### Status

```
usage: main.py status [-h] [--verbose] [--cci CCI] [--all] [--recipe RECIPE [RECIPE ...]] [--json] [--jobs JOBS]

optional arguments:
  -h, --help            show this help message and exit
  --verbose, -v         Verbosity level
  --cci CCI             Path to the conan-center-index repository. Defaults to '../conan-center-index'
  --all, -a             Display all recipes. By default only updatable recipes are displayed.
  --recipe RECIPE [RECIPE ...]
                        Restrict the recipes status to the ones given as arguments.
  --json                Print a JSON instead of a human-readable output.
  --jobs JOBS, -j JOBS  Number of parallel processes.
```

To display a list of all updatable recipe in the CCI repository, run

```bash
python3 main.py status --cci <path-to-cci>
```

### Update

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
