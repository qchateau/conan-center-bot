class CcbError(RuntimeError):
    pass


class UnsupportedRecipe(CcbError):
    pass


class VersionAlreadyExists(CcbError):
    pass


class UnsupportedUpstreamProject(CcbError):
    pass
