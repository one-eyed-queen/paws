from __future__ import annotations

import os
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

from .paths import HOME

PAWS_PY = Path(__file__).resolve().parent.parent / "main.py"
MARK = "# added by paws"
SHELLS = ("fish", "zsh", "bash")


def _runtime():
    venv = Path(__file__).resolve().parent.parent / ".venv/bin/python"
    return str(venv) if venv.exists() else sys.executable


def _launch_command():
    # the console script works from any folder; `-m paws` breaks in a folder that has a paws/ dir in it
    python = Path(_runtime())
    script = python.parent / "paws"
    if script.exists():
        return shlex.quote(str(script))
    py = shlex.quote(str(python))
    if PAWS_PY.exists():
        return f"{py} {shlex.quote(str(PAWS_PY))}"
    return f"{py} -m paws"


NAME_OK = re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,31}")


def valid_name(name: str) -> bool:
    return bool(NAME_OK.fullmatch(name))


def snippet(shell: str, name: str = "paws") -> str:
    command = _launch_command()
    if shell == "fish":
        return f"function {name}\n    {command} $argv\nend\n"
    if shell in ("zsh", "bash"):
        return f'{name}() {{ {command} "$@"; }}\n'
    if shell == "use":
        return command
    return f"# not supported: {shell}; use: {command}"


def my_shell() -> str:
    name = Path(os.environ.get("SHELL", "")).name
    return name if name in SHELLS else "bash"


def install_function(shell: str, name: str = "paws") -> PathResult:
    if shell not in SHELLS:
        raise ValueError(f"don't know how to set up {shell}")
    if not valid_name(name):
        raise ValueError("the command name can use letters, digits, - and _ (and can't start with a digit)")
    text = snippet(shell, name)
    if shell == "fish":
        f = HOME / ".config/fish/functions" / f"{name}.fish"
        if f.exists() and f.read_text().endswith(text):
            return PathResult(shell, f, False, f"`{name}` is already there")
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(f"{MARK}: starts paws. delete this file to undo.\n{text}")
        return PathResult(shell, f, True, f"wrote `{name}`")
    f = _rc_file(shell)
    have = f.read_text() if f.exists() else ""
    if text.strip() in have:
        return PathResult(shell, f, False, f"`{name}` is already there")
    with f.open("a") as fh:
        fh.write(f"\n{MARK}: starts paws\n{text}")
    return PathResult(shell, f, True, f"added `{name}`")


@dataclass
class PathResult:
    shell: str
    file: Path
    changed: bool
    note: str


def _rc_file(shell):
    return HOME / (".zshrc" if shell == "zsh" else ".bashrc")


def _install_fish():
    f = HOME / ".config/fish/conf.d/paws.fish"
    if f.exists():
        return PathResult("fish", f, False, "already set up")
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(
        f"{MARK}: puts ~/.local/bin on fish's PATH so `paws` works. delete this file to undo.\nfish_add_path -g $HOME/.local/bin\n"
    )
    return PathResult("fish", f, True, "wrote it")


def _install_rc(shell):
    f = _rc_file(shell)
    text = f.read_text() if f.exists() else ""
    if ".local/bin" in text:
        return PathResult(shell, f, False, "~/.local/bin is already on PATH there")
    with f.open("a") as fh:
        fh.write(f'\n{MARK}: puts ~/.local/bin on PATH so `paws` works\nexport PATH="$HOME/.local/bin:$PATH"\n')
    return PathResult(shell, f, True, "added a PATH line")


def install_path(shell: str) -> PathResult:
    if shell not in SHELLS:
        raise ValueError(f"don't know how to set up {shell}")
    return _install_fish() if shell == "fish" else _install_rc(shell)


def shells_in_use() -> list[str]:
    found = []
    if (HOME / ".config/fish").is_dir():
        found.append("fish")
    for sh in ("zsh", "bash"):
        if _rc_file(sh).exists():
            found.append(sh)
    return found
