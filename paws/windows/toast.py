"""desktop popups on windows: a tray balloon from powershell, windows 10/11 shows it as a normal notification"""

from __future__ import annotations

import shutil


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


ICONS = {"low": "Info", "normal": "Info", "critical": "Warning"}


def available() -> bool:
    return bool(shutil.which("powershell"))


def command(title: str, body: str = "", urgency: str = "normal", timeout_ms: int = 6000) -> list[str]:
    script = "; ".join(
        [
            "Add-Type -AssemblyName System.Windows.Forms",
            "Add-Type -AssemblyName System.Drawing",
            "$n = New-Object System.Windows.Forms.NotifyIcon",
            "$n.Icon = [System.Drawing.SystemIcons]::Information",
            "$n.Visible = $true",
            f"$n.ShowBalloonTip({int(timeout_ms)}, {_quote(title)}, {_quote(body or ' ')}, "
            f"[System.Windows.Forms.ToolTipIcon]::{ICONS.get(urgency, 'Info')})",
            "Start-Sleep -Milliseconds 1500",
            "$n.Dispose()",
        ]
    )
    return ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", script]
