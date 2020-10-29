_GITHUB_TOKEN = None


def get_github_token():
    return _GITHUB_TOKEN


def set_github_token(token):
    global _GITHUB_TOKEN
    _GITHUB_TOKEN = token