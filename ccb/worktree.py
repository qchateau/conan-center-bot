import os
import tempfile
import shutil

from .recipe import Recipe
from .subprocess import call, check_call


class RecipeInWorktree:
    def __init__(self, recipe):
        self.recipe = recipe
        self.tmpdir = None

    async def __aenter__(self):
        self.tmpdir = tempfile.mkdtemp(prefix="ccb-")
        try:
            await check_call(
                ["git", "worktree", "add", "-q", "--checkout", "--detach", self.tmpdir],
                cwd=self.recipe.path,
            )
            return Recipe(self.tmpdir, self.recipe.name)
        except BaseException:
            self.cleanup()
            raise

    async def __aexit__(self, exc_type, exc_value, exc_traceback):
        await self.cleanup()

    async def cleanup(self):
        if self.tmpdir is None:
            return

        await call(
            ["git", "worktree", "remove", "-f", self.tmpdir], cwd=self.recipe.path
        )
        if os.path.exists(self.tmpdir):
            shutil.rmtree(self.tmpdir)
        self.tmpdir = None
