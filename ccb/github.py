class _GitHubToken:
    value = None


def get_github_token():
    return _GitHubToken.value


def set_github_token(token):
    _GitHubToken.value = token
