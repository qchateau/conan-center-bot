import tempfile
import subprocess

from .recipe import Recipe


class RecipeInWorktree:
    def __init__(self, recipe):
        self.recipe = recipe
        self.tmpdir = None

    def __enter__(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        try:
            subprocess.check_call(
                [
                    "git",
                    "worktree",
                    "add",
                    "-q",
                    "--checkout",
                    "--detach",
                    self.tmpdir.name,
                    "master",
                ],
                cwd=self.recipe.path,
            )
            return Recipe(self.tmpdir.name, self.recipe.name)
        except:
            self.cleanup()
            raise

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.cleanup()

    def cleanup(self):
        if self.tmpdir is None:
            return

        subprocess.call(
            ["git", "worktree", "remove", "-f", self.tmpdir.name], cwd=self.recipe.path
        )
        self.tmpdir.cleanup()