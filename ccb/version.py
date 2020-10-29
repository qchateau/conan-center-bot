import re
import functools

VERSION_RE = re.compile(r"[0-9]+\.[0-9\.]+")
VERSION_DASH_RE = re.compile(r"[0-9]+-[0-9-]+")
VERSION_UNDERSCORE_RE = re.compile(r"[0-9]+_[0-9_]+")


@functools.total_ordering
class Version:
    def __init__(self, version):
        self.original = version
        self.fixed = _fix_version(version)
        self.to_numeric = _to_numeric(self.fixed)

    def __hash__(self):
        return hash(self.original)

    def __eq__(self, other):
        return self.original == other.original

    def __lt__(self, other):
        assert isinstance(other, Version)

        if other.to_numeric is None:
            return False
        if self.to_numeric is None:
            return True
        if self.to_numeric == other.to_numeric:
            return self.original < other.original
        return self.to_numeric < other.to_numeric

    def __str__(self):
        return str(self.original)

    def __repr__(self):
        return f"Version<{self.__str__()}>"


def _fix_version(version):
    version = str(version)

    match = VERSION_RE.search(version)
    if match:
        return match.group(0)

    match = VERSION_DASH_RE.search(version)
    if match:
        return match.group(0).replace("-", ".")

    match = VERSION_UNDERSCORE_RE.search(version)
    if match:
        return match.group(0).replace("_", ".")

    return version


def _to_numeric(version):
    try:
        return tuple(int(x) for x in version.split("."))
    except (ValueError, AttributeError):
        return None