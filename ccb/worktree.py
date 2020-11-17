import os
import tempfile
import subprocess
import shutil

from .recipe import Recipe


class RecipeInWorktree:
    def __init__(self, recipe):
        self.recipe = recipe
        self.tmpdir = None

    def __enter__(self):
        self.tmpdir = tempfile.mkdtemp(prefix="ccb-")
        try:
            subprocess.check_call(
                ["git", "worktree", "add", "-q", "--checkout", "--detach", self.tmpdir],
                cwd=self.recipe.path,
            )
            return Recipe(self.tmpdir, self.recipe.name)
        except BaseException:
            self.cleanup()
            raise

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.cleanup()

    def cleanup(self):
        if self.tmpdir is None:
            return

        subprocess.call(
            ["git", "worktree", "remove", "-f", self.tmpdir], cwd=self.recipe.path
        )
        if os.path.exists(self.tmpdir):
            shutil.rmtree(self.tmpdir)
        self.tmpdir = None
