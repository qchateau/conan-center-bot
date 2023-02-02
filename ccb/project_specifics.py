import re

from .version import Version

# Global tag blacklist, applied to all projects
TAGS_BLACKLIST = [
    re.compile(r"(.*)[\._-]?(rc|alpha|beta|pre|preview)[\._-]?[0-9]*$", re.IGNORECASE),
    re.compile(r"(.*)test(.*)", re.IGNORECASE),
]

# Project-based blacklist, a whitelist must not be defined
PROJECT_TAGS_BLACKLIST = {
    "libpcap": [re.compile(r"(.*)-bp")] + TAGS_BLACKLIST,
    "openssl": [re.compile(r"^OpenSSL-fips-(.*)")] + TAGS_BLACKLIST,
    "libzip": [re.compile(r"^brian-gladman-fcrypt-(.*)")] + TAGS_BLACKLIST,
    "libselinux": [re.compile(r"^[0-9]{8}(.*)")] + TAGS_BLACKLIST,
    "pybind11": [re.compile(r"(.*)b[0-9]+$"), re.compile(r"^(archive|milestones_reached)/")] + TAGS_BLACKLIST,
    "lerc": [re.compile(r"^runtimecore_(.*)")] + TAGS_BLACKLIST,
    "xtensor": [re.compile(r"(.*)-binder[0-9]*$")] + TAGS_BLACKLIST,
    "libunwind": [re.compile(r"^4\.0\.(6|7|9|10)$")] + TAGS_BLACKLIST,
    "ctre": [re.compile(r"^2017$")] + TAGS_BLACKLIST,
    "lz4": [re.compile(r"^r1[0-9][0-9]$")] + TAGS_BLACKLIST,
    "nng": [re.compile(r"^r12$")] + TAGS_BLACKLIST,
    "miniz": [re.compile(r"^v1[0-9][0-9]$")] + TAGS_BLACKLIST,
    "libusb": [re.compile(r"^r[0-9]{3}$")] + TAGS_BLACKLIST,
    "c-ares": [re.compile(r"^curl-(.*)")] + TAGS_BLACKLIST,
    "libtorrent": [re.compile(r"^rc(.*)", re.I)] + TAGS_BLACKLIST,
    "qhull": [re.compile(r"[0-9]{4}\.[0-9]{1,2}")] + TAGS_BLACKLIST,
    "opencv": [re.compile(r"-openvino")] + TAGS_BLACKLIST,
    "gstreamer": [re.compile(r"RELEASE-[0-9]+_[0-9]+_[0-9]+-")] + TAGS_BLACKLIST,
}

# Project-based whitelist, a blacklist must not be defined
PROJECT_TAGS_WHITELIST = {
    "glslang": [re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")],
    "coin-clp": [re.compile(r"^releases\/(.*)")],
    "coin-osi": [re.compile(r"^releases\/(.*)")],
    "coin-utils": [re.compile(r"^releases\/(.*)")],
    "b2": [re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")],
    "hdf5": [re.compile(r"^hdf5-([0-9]+(_[0-9]+)+)$")],
    "libpng": [re.compile(r"^v([0-9]+(\.[0-9]+)+)$")],
    "makefile-project-workspace-creator": [re.compile(r"^MPC_([0-9]+(_[0-9]+)+)")],
    "openimageio": [re.compile(r"^Release-([0-9]+(\.[0-9]+)+)$")],
    "thrust": [re.compile(r"^[0-9]+([\.-][0-9]+)+$")],
    "mbedtls": [re.compile(r"^mbedtls-([0-9]+(\.[0-9]+)+)$")],
    "mcap": [re.compile(r"^releases\/cpp\/(.*)")],
}

# Project-based tag fixer, must convert the tag to a "x.y.z" version
def safe_searcher(pattern, group=0, sep=""):
    def fixer(x):
        match = re.search(pattern, x)
        if match:
            fixed = match.group(group)
            for s in sep:
                fixed = fixed.replace(s, ".")
            return fixed
        return Version.UNKNOWN

    return fixer


PROJECT_TAGS_FIXERS = {
    "argtable3": safe_searcher(r"[0-9]+\.[0-9]+\.[0-9]+"),
    "hdf5": safe_searcher(r"[0-9]+(_[0-9]+)+", sep="_"),
    "thrust": safe_searcher(r"[0-9]+([\.-][0-9]+)+", sep=".-"),
}
