"""Wait for the backend to answer before anything starts talking to it.

The startup scripts launch uvicorn and the Vite dev server back to back, but the
two do not come up together. Vite is serving in under a second; the backend
spends several seconds importing FastAPI and running its lifespan - migrate,
restore settings, open the graph store - and uvicorn binds its socket only after
all of that has finished.

The UI polls /api/telemetry/summary every 1.5s from first paint, so every poll
inside that window is proxied to a port nothing is listening on yet. Vite logs
each one as `http proxy error: ... ECONNREFUSED 127.0.0.1:8787` with a stack
trace, which reads like a broken build and buries any real error underneath it.

Nothing is wrong in that case except the order: the frontend was started first.
So the startup scripts wait here, between launching the backend and launching
the UI.

    python backend/scripts/wait_for_backend.py 8787 [--timeout 90] [--pid N]

Why /health rather than a TCP connect: uvicorn runs the lifespan before it
binds, so an open port is very nearly proof already - but very nearly is not a
check. A 200 from /health proves the app is ours and is answering requests, and
it is the same thing the operator would reach for by hand.
"""

from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
import time
import urllib.error
import urllib.request

WINDOWS = platform.system() == "Windows"

POLL_S = 0.25
# Per-probe, not overall: a request that hangs must not eat the whole budget.
PROBE_TIMEOUT_S = 2.0
# Long enough for a cold import on a machine that was just switched on - the
# slow case is a first run that also builds the embedding cache - and short
# enough that a backend which is never coming up is not a five-minute wait.
DEFAULT_TIMEOUT_S = 90.0
# Silence looks like a hang. Say what is being waited for, at intervals.
PROGRESS_EVERY_S = 5.0


def answers(port: int) -> bool:
    """True once /health returns 200 on this port.

    Every failure means the same thing here - not ready yet - so they collapse
    into one False. A non-2xx raises HTTPError, which is a URLError, and a
    refused connection raises URLError wrapping the OSError.
    """
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health",
                                    timeout=PROBE_TIMEOUT_S) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError, TimeoutError):
        return False


def alive(pid: int) -> bool:
    """Is the process we are waiting on still running?

    A uvicorn that dies during boot - a bad .env, an unreadable graph store -
    would otherwise be waited on until the timeout, and a slow failure reads to
    the operator as a slow start.

    The pid must be one the OS itself issued. A pid from a shell that keeps its
    own namespace - Git Bash and Cygwin both do - names nothing here, and this
    would then report a healthy backend as dead the moment it was asked. The
    callers are responsible for only passing a pid that the OS will recognise;
    startup.sh checks `uname` before it does.
    """
    if WINDOWS:
        try:
            out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
                                 capture_output=True, text=True, timeout=15)
        except (OSError, subprocess.SubprocessError):
            return True  # cannot tell; keep waiting rather than abort a good boot
        return str(pid) in (out.stdout or "")
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # alive, just not ours to signal
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Wait until the backend answers /health on a port")
    parser.add_argument("port", type=int)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S,
                        help=f"seconds to wait (default {DEFAULT_TIMEOUT_S:.0f})")
    parser.add_argument("--pid", type=int, default=None,
                        help="give up as soon as this process exits; must be a pid "
                             "in the OS namespace, not a Git Bash or Cygwin one")
    args = parser.parse_args()

    print(f"Waiting for the backend on http://127.0.0.1:{args.port} ...")
    started = time.monotonic()
    deadline = started + args.timeout
    announced = started

    while time.monotonic() < deadline:
        if answers(args.port):
            print(f"  backend ready after {time.monotonic() - started:.1f}s")
            return 0

        if args.pid is not None and not alive(args.pid):
            print(f"  backend process {args.pid} exited before it answered.")
            print("  Its output above has the traceback.")
            return 1

        now = time.monotonic()
        if now - announced >= PROGRESS_EVERY_S:
            announced = now
            print(f"  still starting ({now - started:.0f}s elapsed)")
        time.sleep(POLL_S)

    print(f"  backend did not answer within {args.timeout:.0f}s.")
    print("  Check the backend window, or start it in the foreground to see why:")
    if WINDOWS:
        print(rf"    cd backend && ..\.venv\Scripts\python.exe -m uvicorn app.main:app "
              rf"--port {args.port}")
    else:
        print(f"    cd backend && ../.venv/bin/python -m uvicorn app.main:app "
              f"--port {args.port}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
