# conan-center-bot

This is a script to help update recipes in conan-center-index.
CUrrently is only supports updating recipes that use GitHub.

## GitHub token

You'll need a github token to allow more than 60 requests per hour to `api.github.com`.

Create one here: https://github.com/settings/tokens

## How does it work

The script will try to locate the most recent version in CCI, and the most
recent version in GitHub. If GitHub contains a version that is more recent than
the latest one on CCI, the script will add it to the CCI repository.

After you ran the script:

- Move to CCI
- Verify and maybe tweak the diff
- Run the test
- Commit
- Open a PR on CCI

## Limitations

- Only projects on GitHub are supported.
- Some versioning patterns are too specific to be supported.
- Recipes require a config.yml file.
- Still requires manual operations.

## Update everything

```bash
python3 main.py <path-to-conan-center-index-repo> --github-token=<github-token>
```

## Update and test a single recipe

It's up to you to configure the correct conan hooks for the test.

```bash
python3 main.py <path-to-conan-center-index-repo> --github-token=<github-token> --recipe <recipe-name> --test
```
