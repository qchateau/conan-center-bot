def format_duration(duration):
    hours = int(duration // 3600)
    duration -= hours * 3600
    minutes = int(duration // 60)
    seconds = duration - minutes * 60

    if hours > 0:
        return f"{hours}h {minutes}m"
    if minutes > 0:
        return f"{minutes}m {int(seconds)}s"
    return f"{seconds:.1f}s"


def yn_question(question, default):
    default_txt = "[Y/n]" if default else "[y/N]"
    while True:
        txt = input(f"{question} {default_txt} ").strip().lower()
        if not txt:
            return default
        elif txt[0] == "y":
            return True
        elif txt[0] == "n":
            return False
