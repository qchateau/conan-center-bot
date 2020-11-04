import re

# Global tag blacklist, applied to all projects
TAGS_BLACKLIST = [
    re.compile(r"(.*)[\.-_]?(rc|alpha|beta|pre|preview)[\.-_]?[0-9]*$", re.IGNORECASE),
    re.compile(r"(.*)test(.*)", re.IGNORECASE),
]

# Project-based blacklist, a whitelist must not be defined
PROJECT_TAGS_BLACKLIST = {
    "libpcap": [re.compile(r"(.*)-bp")],
    "openssl": [re.compile(r"^OpenSSL-fips-(.*)")],
    "libzip": [re.compile(r"^brian-gladman-fcrypt-(.*)")],
    "libselinux": [re.compile(r"^[0-9]{8}(.*)")],
    "pybind11": [re.compile(r"(.*)b[0-9]+$")],
    "lerc": [re.compile(r"^runtimecore_(.*)")],
    "xtensor": [re.compile(r"(.*)-binder[0-9]*$")],
}

# Project-based whitelist, a blacklist must not be defined
PROJECT_TAGS_WHITELIST = {
    "glslang": [re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")],
    "coin-clp": [re.compile(r"^releases\/(.*)")],
    "coin-osi": [re.compile(r"^releases\/(.*)")],
    "coin-utils": [re.compile(r"^releases\/(.*)")],
}
