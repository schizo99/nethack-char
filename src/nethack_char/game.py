"""Log in to a dgamelaunch NetHack server over SSH, check the starting stats, then save or quit."""

import argparse
import getpass
import json
import os
import re
import sys
import time

import paramiko
import pyte

COLS, ROWS = 132, 40
MENU_RE = re.compile(r"Logged in as:")
STAT_NAMES = ("St", "Dx", "Co", "In", "Wi", "Ch")
STATS_RE = re.compile(
    r"St:(\d+(?:/(?:\d+|\*\*))?)\s+Dx:(\d+)\s+Co:(\d+)\s+In:(\d+)\s+Wi:(\d+)\s+Ch:(\d+)"
)


class Session:
    """Interactive shell channel backed by a virtual terminal so the screen can be read."""

    def __init__(self, channel: paramiko.Channel):
        self.channel = channel
        self.screen = pyte.Screen(COLS, ROWS)
        self.stream = pyte.ByteStream(self.screen)

    def text(self) -> str:
        return "\n".join(self.screen.display)

    def send(self, keys: str) -> None:
        self.channel.send(keys.encode())

    def pump(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self.channel.recv_ready():
                self.stream.feed(self.channel.recv(65536))
            elif self.channel.closed or self.channel.exit_status_ready():
                raise ConnectionError("Server closed the connection")
            else:
                time.sleep(0.05)

    def wait_for(self, pattern: str | re.Pattern, timeout: float = 15) -> re.Match:
        end = time.monotonic() + timeout
        while not (match := re.search(pattern, self.text())):
            if time.monotonic() > end:
                raise TimeoutError(f"Timed out waiting for {pattern!r}. Screen:\n{self.text()}")
            self.pump(0.05)
        return match


def stat_value(raw: str | int) -> float:
    """Make stats comparable; exceptional strength 18/xx sorts between 18 and 19."""
    base, _, extra = str(raw).partition("/")
    if not extra:
        return int(base)
    return int(base) + (100 if extra == "**" else int(extra)) / 1000


def stats_ok(stats: dict[str, str], minimums: dict[str, str | int]) -> bool:
    return all(stat_value(stats[name]) >= stat_value(minimum) for name, minimum in minimums.items())


def return_to_menu(session: Session, timeout: float = 60) -> None:
    """Click through end-of-game prompts and screens until the dgamelaunch menu is back."""
    end = time.monotonic() + timeout
    while not MENU_RE.search(session.text()):
        if time.monotonic() > end:
            raise TimeoutError(f"Did not return to the menu. Screen:\n{session.text()}")
        # 'q' on a [ynq] prompt skips the remaining "identify/show" questions.
        session.send("q" if "[ynq]" in session.text() else "\r")
        session.pump(0.7)


def save_game(session: Session) -> None:
    session.send("S")
    session.wait_for(r"Really save\?")
    session.send("y")
    return_to_menu(session)


def quit_game(session: Session) -> None:
    session.send("#")
    session.pump(0.5)
    session.send("q")
    try:
        session.wait_for(r"Really quit", timeout=2)
    except TimeoutError:
        session.send("\r")
        session.wait_for(r"Really quit")
    session.send("y")
    return_to_menu(session)


def roll(session: Session, minimums: dict[str, str | int], max_attempts: int) -> bool:
    session.wait_for(MENU_RE)
    attempt = 0
    # max_attempts <= 0 means keep re-rolling until the stats are met.
    while max_attempts <= 0 or attempt < max_attempts:
        attempt += 1
        session.send("p")
        session.wait_for(r"Is this ok\?")
        session.send("y")
        stats = dict(zip(STAT_NAMES, session.wait_for(STATS_RE).groups()))
        ok = stats_ok(stats, minimums)
        print(f"Attempt {attempt}: {' '.join(f'{k}:{v}' for k, v in stats.items())} -> {'OK' if ok else 'not OK'}")

        # Dismiss the intro text before issuing game commands.
        for _ in range(3):
            session.send("\x1b")
            session.pump(0.5)

        if ok:
            save_game(session)
            print("Game saved.")
            return True
        quit_game(session)
        print("Game quit.")
    return False


def connect(cfg: dict, ssh_password: str | None) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    # Unknown hosts are rejected; the host must already be in ~/.ssh/known_hosts.
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.connect(
        hostname=cfg["host"],
        port=cfg.get("port", 22),
        username=cfg["username"],
        key_filename=os.path.expanduser(cfg["key_filename"]) if cfg.get("key_filename") else None,
        password=ssh_password,
        # With a password given, skip key/agent auth so it isn't rejected for too many attempts.
        look_for_keys=ssh_password is None,
        allow_agent=ssh_password is None,
        timeout=15,
    )
    return client


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", help="Path to JSON config file")
    parser.add_argument(
        "--ssh-password",
        action="store_true",
        help="Log in to SSH with a password (from SSH_PASSWORD or prompted) instead of a key",
    )
    args = parser.parse_args()

    with open(args.config) as f:
        cfg = json.load(f)
    ssh_password = None
    if args.ssh_password or "SSH_PASSWORD" in os.environ:
        ssh_password = os.environ.get("SSH_PASSWORD") or getpass.getpass(
            f"SSH password for {cfg['username']}@{cfg['host']}: "
        )
    password = os.environ.get("NETHACK_PASSWORD") or getpass.getpass(f"NetHack password for {cfg['nethack_user']}: ")

    client = connect(cfg, ssh_password)
    try:
        channel = client.get_transport().open_session()
        channel.get_pty(term="xterm-256color", width=COLS, height=ROWS)
        channel.update_environment({"DGLAUTH": f"{cfg['nethack_user']}:{password}"})
        channel.invoke_shell()
        session = Session(channel)

        saved = roll(session, cfg.get("min_stats", {}), cfg.get("max_attempts", 0))
        session.send("q")  # leave dgamelaunch
        return 0 if saved else 1
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
