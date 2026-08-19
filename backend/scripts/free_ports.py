"""Reclaim the ports the app needs, before pre-flight looks at them.

A restart that aborts because the previous run is still holding 8787 is the
single most common way this app refuses to start, and the fix - find the pid,
kill it, try again - is the same three commands every time. Pre-flight is right
to fail on a busy port; it is the wrong place to fix one, because a check that
repairs what it is checking cannot be trusted to report.

So this runs BEFORE pre-flight and leaves pre-flight's assertion honest.

What it will not do:

* **Kill silently.** Every process it stops is printed with its pid and image
  name first. A one-click script that kills something the operator cared about
  and says nothing is worse than one that fails to start.
* **Kill by name.** Only a process actually LISTENING on one of the named ports
  is a candidate. Matching on "python" or "node" would reach across every other
  checkout on the machine.
* **Assume it worked.** The port is re-tested after the kill, and a port that is
  still held is a non-zero exit, not a shrug.

    python backend/scripts/free_ports.py 8787 5173 [--dry-run]
"""

from __future__ import annotations

import argparse
import os
import platform
import signal
import socket
import subprocess
import sys
import time

WINDOWS = platform.system() == "Windows"

# A killed process does not release its socket instantly; the kernel needs a
# moment even with SIGKILL. Long enough to be reliable, short enough that a
# genuinely stuck port still fails the startup quickly.
RELEASE_TIMEOUT_S = 10.0
POLL_S = 0.25
# Between asking a process to stop and insisting.
GRACE_S = 3.0


def _run(cmd: list[str]) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout or ""


def _can_bind(family: int, address: str, port: int) -> bool:
    """True if nothing holds this port on this address family.

    Deliberately no SO_REUSEADDR. On Windows it does not mean what it means on
    Linux - it permits binding a port another socket already holds - so setting
    it turns this test into one that always says "free".
    """
    try:
        sock = socket.socket(family, socket.SOCK_STREAM)
    except OSError:
        return True  # no support for this family; it cannot be holding anything
    with sock:
        if family == socket.AF_INET6:
            try:
                sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            except OSError:
                pass
        try:
            sock.bind((address, port))
            return True
        except OSError:
            return False


def is_free(port: int) -> bool:
    """Free on BOTH families, or it is not free.

    Vite listens on ::1 by default, and an IPv4-only check calls that port free
    and then watches the launch fail with EADDRINUSE. Checking one family is how
    a port-reclaimer ends up worse than no port-reclaimer at all.
    """
    return (_can_bind(socket.AF_INET, "127.0.0.1", port)
            and _can_bind(socket.AF_INET6, "::1", port))


def _listeners_windows(port: int) -> set[int]:
    """Parse plain `netstat -ano`, with no -p filter.

    `-p TCP` selects the IPv4 table only - Windows treats TCPv6 as a separate
    protocol - so filtering there makes a listener on [::1] invisible, which is
    exactly where Vite lives.
    """
    pids: set[int] = set()
    for line in _run(["netstat", "-ano"]).splitlines():
        parts = line.split()
        # proto, local, foreign, state, pid
        if len(parts) < 5 or not parts[0].upper().startswith("TCP"):
            continue
        if parts[3].upper() != "LISTENING":
            continue
        # The LOCAL column only. A foreign address ending in the same port is a
        # client of ours, not the thing holding it. rsplit handles both
        # "127.0.0.1:5173" and "[::1]:5173".
        if parts[1].rsplit(":", 1)[-1] != str(port):
            continue
        if parts[4].isdigit():
            pids.add(int(parts[4]))
    return pids


def _listeners_posix(port: int) -> set[int]:
    # -iTCP:<port> covers both families; lsof has no IPv4/IPv6 split to trip on.
    raw = _run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"])
    return {int(p) for p in raw.split() if p.strip().isdigit()}


def listeners(port: int) -> set[int]:
    pids = _listeners_windows(port) if WINDOWS else _listeners_posix(port)
    # Never take out the script doing the reclaiming, or the shell that ran it.
    return pids - {os.getpid(), os.getppid()}


def process_name(pid: int) -> str:
    if WINDOWS:
        raw = _run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"])
        first = raw.strip().splitlines()[0] if raw.strip() else ""
        if first.startswith('"'):
            return first.split('","')[0].strip('"')
        return "unknown"
    return _run(["ps", "-p", str(pid), "-o", "comm="]).strip() or "unknown"


def terminate(pid: int) -> None:
    """Ask, then insist. A uvicorn given SIGTERM closes its Kuzu handle on the
    way out; one that is SIGKILLed leaves the graph store to recover on open."""
    if WINDOWS:
        # No POSIX signals worth the name: taskkill without /F asks a GUI app
        # politely and does nothing to a console process, so /T /F is the only
        # thing that reliably takes the child shells with it.
        _run(["taskkill", "/PID", str(pid), "/T", "/F"])
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return
    deadline = time.monotonic() + GRACE_S
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(POLL_S)
    try:
        os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def wait_free(port: int, timeout: float = RELEASE_TIMEOUT_S) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if is_free(port):
            return True
        time.sleep(POLL_S)
    return is_free(port)


def reclaim(port: int, dry_run: bool = False) -> bool:
    if is_free(port):
        print(f"  port {port:<5} free")
        return True

    pids = listeners(port)
    if not pids:
        # Held, but by nothing we can name: a socket in TIME_WAIT, or a process
        # owned by another user. Killing is not an option and pretending it is
        # would produce a confusing failure two steps later.
        print(f"  port {port:<5} IN USE by no process we can identify "
              f"(TIME_WAIT, or owned by another user)")
        return False

    for pid in sorted(pids):
        name = process_name(pid)
        if dry_run:
            print(f"  port {port:<5} would stop pid {pid} ({name})")
            continue
        print(f"  port {port:<5} stopping pid {pid} ({name})")
        terminate(pid)

    if dry_run:
        return True

    if wait_free(port):
        print(f"  port {port:<5} reclaimed")
        return True
    print(f"  port {port:<5} STILL IN USE after stopping {sorted(pids)}")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Free the ports the app needs")
    parser.add_argument("ports", nargs="+", type=int)
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would be stopped, stop nothing")
    args = parser.parse_args()

    print("Reclaiming ports...")
    ok = True
    for port in args.ports:
        ok &= reclaim(port, dry_run=args.dry_run)

    if not ok:
        print("")
        print("Could not free every port. Nothing has been started.")
        print("Find the holder and stop it yourself, then re-run:")
        for port in args.ports:
            print(f"  netstat -ano | findstr :{port}" if WINDOWS
                  else f"  lsof -nP -iTCP:{port} -sTCP:LISTEN")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
