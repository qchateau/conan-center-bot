from asyncio.subprocess import create_subprocess_exec, PIPE


class SubprocessError(RuntimeError):
    pass


async def run(cmd, **kwargs):
    return await create_subprocess_exec(cmd[0], *cmd[1:], **kwargs)


async def call(cmd, **kwargs):
    process = await run(cmd=cmd, **kwargs)
    return await process.wait()


async def check_call(cmd, **kwargs):
    code = await call(cmd=cmd, **kwargs)
    if code != 0:
        raise SubprocessError()


async def check_output(cmd, **kwargs):
    process = await run(cmd=cmd, stdout=PIPE, **kwargs)
    code = await process.wait()
    if code != 0:
        raise SubprocessError()
    return await process.stdout.read()
