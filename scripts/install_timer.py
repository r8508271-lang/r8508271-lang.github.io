#!/usr/bin/env python3
"""Install a local systemd user timer; no AI service is involved."""

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
UNIT = "anonymous-gallery-sync"
MARKER = "# Managed by anonymous-gallery scripts/install_timer.py\n"


def quote_path(path: Path) -> str:
    value = str(path)
    if any(character in value for character in "\n\r\0$"):
        raise SystemExit("Unsupported character in installation path.")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%") + '"'


def main() -> None:
    if not (ROOT / ".local/config.json").is_file():
        raise SystemExit("Configure and test gallery.py publish before installing the timer.")
    destination = Path.home() / ".config/systemd/user"
    service = MARKER + f"""[Unit]
Description=Synchronize the anonymous video gallery from Google Drive

[Service]
Type=oneshot
WorkingDirectory={str(ROOT).replace('%', '%%')}
ExecStart={quote_path(Path(sys.executable).resolve())} {quote_path(ROOT / 'scripts/gallery.py')} publish --scheduled
Environment=PATH=/usr/local/bin:/usr/bin:/bin
Environment=PYTHONUNBUFFERED=1
UMask=0077
TimeoutStartSec=5min
"""
    timer = MARKER + f"""[Unit]
Description=Check the anonymous gallery every minute

[Timer]
OnStartupSec=1min
OnUnitActiveSec=1min
AccuracySec=1s
Unit={UNIT}.service

[Install]
WantedBy=timers.target
"""
    units = {f"{UNIT}.service": service, f"{UNIT}.timer": timer}
    # Never replace an unrelated unit with the same name.
    for name in units:
        target = destination / name
        if target.exists() and not target.read_text().startswith(MARKER):
            raise SystemExit(f"Refusing to replace an unmanaged {name}.")
    destination.mkdir(parents=True, exist_ok=True)
    for name, content in units.items():
        (destination / name).write_text(content)
    subprocess.run(["systemd-analyze", "--user", "verify", *[str(destination / name) for name in units]], check=True)
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", UNIT + ".timer"], check=True)
    subprocess.run(["systemctl", "--user", "is-active", "--quiet", UNIT + ".timer"], check=True)
    print("Local timer installed: every minute, with a 10-minute automatic publish interval.")
    print("Status: systemctl --user status " + UNIT + ".timer")
    print("Logs: journalctl --user -u " + UNIT + ".service -n 30 --no-pager")
    print("Stop: systemctl --user disable --now " + UNIT + ".timer")


if __name__ == "__main__":
    main()
