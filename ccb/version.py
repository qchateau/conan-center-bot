import re
import functools
from datetime import datetime
from typing import Optional, NamedTuple

VERSION_DATE_RE = re.compile(r"([0-9]{4})[\.-_]?([0-9]{2})[\.-_]?([0-9]{2})")
VERSION_RE = re.compile(r"[0-9]+(\.[0-9]+)+")
VERSION_DASH_RE = re.compile(r"[0-9]+(-[0-9]+)+")
VERSION_COUNTER_RE = re.compile(r"^[rv]?([0-9]+)$")
VERSION_UNDERSCORE_RE = re.compile(r"[0-9]+(_[0-9]+)+")


class VersionMeta(NamedTuple):
    date: Optional[datetime] = None
    commit_count: Optional[int] = None


@functools.total_ordering
class Version:
    UNKNOWN = "unknown"

    def __init__(self, version=UNKNOWN, fixer=None, meta=VersionMeta()):
        if fixer is None:
            fixer = _fix_version
        self.original = version
        self.fixed = fixer(version)
        self.to_numeric = _to_numeric(self.fixed)
        self.is_date = bool(
            VERSION_DATE_RE.search(
                self.fixed if self.fixed != self.UNKNOWN else self.original
            )
        )
        self.meta = meta

    @property
    def unknown(self):
        return self.original == self.UNKNOWN

    def inconsistent_with(self, other):
        return not other.unknown and not self.unknown and other.is_date != self.is_date

    def consistent_with(self, other):
        return not other.unknown and not self.unknown and other.is_date == self.is_date

    def updatable_to(self, other):
        return self.consistent_with(other) and (other > self)

    def up_to_date_with(self, other):
        return self.consistent_with(other) and (other <= self)

    def __hash__(self):
        return hash(self.fixed)

    def __eq__(self, other):
        return self.fixed == other.fixed

    def __lt__(self, other):
        assert isinstance(other, Version)

        if other.to_numeric is None:
            return False
        if self.to_numeric is None:
            return True
        if self.is_date != other.is_date:
            # consider dates as old versions to avoid false positive
            return self.is_date
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

    match = VERSION_DATE_RE.search(version)
    if match:
        return "".join(match.groups())

    match = VERSION_COUNTER_RE.search(version)
    if match:
        return match.group(1)

    return Version.UNKNOWN


def _to_numeric(version):
    try:
        return tuple(int(x) for x in version.split("."))
    except (ValueError, AttributeError):
        return None
