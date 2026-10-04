from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from collections.abc import Mapping

from ..windows import IS_WINDOWS
from .argv import build_argv
from .pick import candidates, current_terminal
from .script import paws_argv, shell_command

WAIT = 1.5


@dataclass
class Attempt:
    terminal: str
    argv: list[str]
    ok: bool
    detail: str = ""


@dataclass
class Result:
    ok: bool
    terminal: str | None = None
    attempts: list[Attempt] = field(default_factory=list)

    def explain(self) -> str:
        if self.ok:
            return f"opened in {self.terminal}"
        if not self.attempts:
            return (
                "no terminal emulator found. run `paws` inside a terminal, "
                "or set PAWS_TERMINAL to one (e.g. PAWS_TERMINAL=kitty)."
            )
        lines = ["couldn't open a terminal window:"]
        lines += [f"  {a.terminal}: {a.detail or 'failed'}" for a in self.attempts]
        lines.append("run `paws` inside a terminal instead, or set PAWS_TERMINAL to one that works.")
        return "\n".join(lines)


def _windows_launch(terminal, env):
    """windows: argv straight to windows terminal / a new console, no shell string. PAWS_HOLD makes paws itself keep
    the window open when it fails, which is what the sh -c wrapper does on linux"""
    from ..windows import terminal as windows_terminal

    argv = windows_terminal.build_argv(terminal, paws_argv())
    env = {**env, windows_terminal.HOLD: "1"}
    how = {"creationflags": windows_terminal.creation_flags(terminal)}
    if terminal == "console":  # its stdio must be the new console, redirecting it would leave a blank window
        how.update(stdin=None, stdout=None, stderr=None)
    return argv, env, how


def try_terminal(terminal, command, env, wait):
    if IS_WINDOWS:
        argv, env, how = _windows_launch(terminal, env)
    else:
        argv, how = build_argv(terminal, command), {"start_new_session": True}
    stderr_file = tempfile.TemporaryFile()
    try:
        process = subprocess.Popen(
            argv,
            **{"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": stderr_file, **how},
            env=dict(env),
        )
    except OSError as error:
        stderr_file.close()
        return Attempt(terminal, argv, False, str(error))
    try:
        return_code = process.wait(timeout=wait)
    except subprocess.TimeoutExpired:
        stderr_file.close()
        return Attempt(terminal, argv, True, "running")
    stderr_file.seek(0)
    message = stderr_file.read().decode(errors="replace").strip()
    stderr_file.close()
    if return_code == 0:
        return Attempt(terminal, argv, True, "started (forked into its server)")
    last = message.splitlines()[-1] if message else ""
    return Attempt(terminal, argv, False, f"exited with code {return_code}" + (f": {last}" if last else ""))


def open_window(env: Mapping[str, str] | None = None, wait: float = WAIT) -> Result:
    env = os.environ if env is None else env
    command = shell_command()
    result = Result(False)
    for term in candidates(env):
        attempt = try_terminal(term, command, env, wait)
        result.attempts.append(attempt)
        if attempt.ok:
            result.ok, result.terminal = True, term
            break
    return result


def describe(env: Mapping[str, str] | None = None) -> dict:
    env = os.environ if env is None else env
    found = candidates(env)
    return {
        "in_terminal": current_terminal(env),
        "candidates": found,
        "would_use": found[0] if found else None,
        "argv": (_windows_launch(found[0], env)[0] if IS_WINDOWS else build_argv(found[0], shell_command()))
        if found
        else None,
    }
