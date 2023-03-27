from asyncio.subprocess import create_subprocess_exec, PIPE


class SubprocessError(RuntimeError):
    def __init__(self, process):
        super().__init__("subprocess error")
        self.process = process


async def run(cmd, **kwargs):
    return await create_subprocess_exec(cmd[0], *cmd[1:], **kwargs)


async def call(cmd, **kwargs):
    process = await run(cmd=cmd, **kwargs)
    return await process.wait()


async def check_call(cmd, **kwargs):
    process = await run(cmd=cmd, **kwargs)
    code = await process.wait()
    if code != 0:
        print(f"error {code} for command {cmd}")
        exit(-1)
        raise SubprocessError(process)


async def check_output(cmd, **kwargs):
    process = await run(cmd=cmd, stdout=PIPE, **kwargs)
    stdout, _ = await process.communicate()
    code = await process.wait()
    if code != 0:
        raise SubprocessError(process)
    return stdout.decode()
