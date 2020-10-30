class CcbError(RuntimeError):
    pass


class RecipeError(CcbError):
    pass


class VersionAlreadyExists(CcbError):
    pass


class TestFailed(CcbError):
    def __init__(self, output):
        super().__init__("Test failed")
        self.output = output
