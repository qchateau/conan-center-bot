import tempfile
import subprocess

from .recipe import Recipe


class RecipeInWorktree:
    def __init__(self, recipe, branch_name):
        self.recipe = recipe
        self.branch_name = branch_name

    def __enter__(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        subprocess.check_call(
            [
                "git",
                "worktree",
                "add",
                "-q",
                "--checkout",
                "-b",
                self.branch_name,
                self.tmpdir.name,
                "master",
            ],
            cwd=self.recipe.path,
        )
        return Recipe(self.tmpdir.name, self.recipe.name)

    def __exit__(self, exc_type, exc_value, exc_traceback):
        subprocess.check_output(
            ["git", "worktree", "remove", "-f", self.tmpdir.name], cwd=self.recipe.path
        )
        self.tmpdir.cleanup()
