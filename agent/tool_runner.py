"""Запуск команд оболочки с таймаутом."""

from __future__ import annotations

import asyncio
import os
import signal

_DEFAULT_TIMEOUT_SECONDS = 60.0


def _kill_process_group(process: asyncio.subprocess.Process) -> None:
    if process.pid is None:
        process.kill()
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        process.kill()


class ToolRunner:
    """Выполняет одну shell-команду и возвращает код, stdout и stderr."""

    def __init__(self, timeout: float = _DEFAULT_TIMEOUT_SECONDS) -> None:
        self.timeout = timeout

    async def execute(self, command: str) -> tuple[int, str, str]:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        communicate = asyncio.create_task(process.communicate())
        timer = asyncio.create_task(asyncio.sleep(self.timeout))
        done, _pending = await asyncio.wait(
            {communicate, timer},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if communicate not in done:
            _kill_process_group(process)
            stdout, stderr = await communicate
            message = f"Command timed out after {self.timeout:g} seconds"
            err_text = stderr.decode("utf-8", errors="replace")
            if err_text and not err_text.endswith("\n"):
                err_text += "\n"
            return 124, stdout.decode("utf-8", errors="replace"), err_text + message
        timer.cancel()
        await asyncio.gather(timer, return_exceptions=True)
        stdout, stderr = communicate.result()
        return (
            process.returncode if process.returncode is not None else 1,
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
        )
