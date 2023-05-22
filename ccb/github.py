import logging
import requests

logger = logging.getLogger(__name__)

class _GitHubToken:
    value = None


def get_github_token():
    return _GitHubToken.value


def set_github_token(token):
    _GitHubToken.value = token
    print_github_token_rate_limit()


def print_github_token_rate_limit():
    github_token = get_github_token()
    headers = {"Accept": "application/vnd.github.v3+json"}
    if github_token:
        headers["Authorization"] = f"token {github_token}"
    res = requests.get(" https://api.github.com/rate_limit", headers=headers, timeout=1)
    logger.warning("github rate limits: %s", res.json())
