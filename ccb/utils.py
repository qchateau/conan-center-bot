import asyncio


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


def return_on_exc(logger, value):
    class Wrapper:
        def __init__(self, function):
            self.function = function

        def __call__(self, *args, **kwargs):
            try:
                return self.function(*args, **kwargs)
            except Exception as exc:
                logger.debug("exception in %s: %s", self.function.__name__, exc)
                return value

    return Wrapper


class LockStorage:
    def __init__(self):
        self.data = dict()

    def get(self, loop=asyncio.get_event_loop()):
        if loop not in self.data:
            self.data[loop] = asyncio.Lock()
        return self.data[loop]


class SemaphoneStorage:
    def __init__(self, initial_count):
        self.initial_count = initial_count
        self.data = dict()

    def get(self, loop=asyncio.get_event_loop()):
        if loop not in self.data:
            self.data[loop] = asyncio.Semaphore(self.initial_count)
        return self.data[loop]
