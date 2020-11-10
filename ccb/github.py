_TOKEN = None


def get_github_token():
    return _TOKEN


def set_github_token(token):
    global _TOKEN
    _TOKEN = token
