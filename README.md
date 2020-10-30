# conan-center-bot

This is a script to help update recipes in conan-center-index.
Currently is only supports updating recipes that use GitHub.

## How does it work

The script will try to locate the most recent version in CCI, and the most recent version in GitHub. If GitHub contains a version that is more recent than the latest one on CCI, the script will add it to the CCI repository,
in a new branch and commit it.

After you ran the script:

- Verify and maybe tweak the diff in the nea branch
- Open a PR on CCI

## Limitations

- Only projects on GitHub are supported.
- Some versioning patterns are too specific to be supported.
- Recipes require a config.yml file.
- Still requires manual operations.

## Update, test and push everything

```bash
python3 main.py <path-to-conan-center-index-repo>  --test --push -f
```

## Update, test and push a single recipe

It's up to you to configure the correct conan hooks for the test.

```bash
python3 main.py <path-to-conan-center-index-repo> --recipe <recipe-name> --test --push -f
```
