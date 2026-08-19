"""Pre-flight validation (PRD FR-20).

Fails fast naming the exact missing item. Run standalone or from the startup
scripts. Every check that can be wrong at 2am before a demo is checked here.
Model aliases are chosen at runtime in the settings drawer, so an unset role is
reported as a warning rather than a failure.

    python backend/scripts/preflight.py
    python backend/scripts/preflight.py --skip-node
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"
MIN_PYTHON = (3, 11)
MIN_NODE = 20


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    fatal: bool = True

    @property
    def marker(self) -> str:
        if self.ok:
            return f"{GREEN}PASS{RESET}"
        return f"{RED}FAIL{RESET}" if self.fatal else f"{YELLOW}WARN{RESET}"


def check_python() -> Check:
    v = sys.version_info
    ok = (v.major, v.minor) >= MIN_PYTHON
    return Check("Python version", ok,
                 f"{v.major}.{v.minor}.{v.micro} (need >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]})")


def check_venv() -> Check:
    active = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    return Check("Virtual environment", active,
                 sys.prefix if active else "not active - run: python -m venv .venv && "
                 "source .venv/Scripts/activate (Windows) or .venv/bin/activate (POSIX)")


def check_node(skip: bool) -> Check:
    if skip:
        return Check("Node.js", True, "skipped", fatal=False)
    exe = shutil.which("node")
    if not exe:
        return Check("Node.js", False, f"not found on PATH (need >= {MIN_NODE}, 22.x recommended)")
    try:
        raw = subprocess.run([exe, "--version"], capture_output=True, text=True,
                             timeout=15).stdout.strip()
        major = int(raw.lstrip("v").split(".")[0])
        return Check("Node.js", major >= MIN_NODE,
                     f"{raw} (need >= {MIN_NODE}, 22.x recommended)")
    except (ValueError, IndexError, subprocess.SubprocessError) as exc:
        return Check("Node.js", False, f"version unreadable: {exc}")


def check_port(port: int) -> Check:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
            return Check(f"Port {port} free", True, "available")
        except OSError as exc:
            return Check(f"Port {port} free", False, f"in use ({exc.strerror or exc})")


def check_data_dir(path: Path) -> Check:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return Check("Data directory writable", True, str(path))
    except OSError as exc:
        return Check("Data directory writable", False, f"{path}: {exc}")


def check_env_file() -> Check:
    env = REPO_ROOT / ".env"
    if env.exists():
        return Check(".env present", True, str(env))
    return Check(".env present", False,
                 f"missing - copy {REPO_ROOT / '.env.example'} to .env and fill in")


def check_gateway(settings) -> tuple[Check, list[str]]:
    """Reachability plus the live model catalogue."""
    import httpx

    if not settings.gateway_api_key:
        return Check("LLM gateway reachable", False,
                     "GATEWAY_API_KEY is empty - set it in .env"), []
    url = f"{settings.openai_base_url}/models"
    try:
        with httpx.Client(verify=settings.ssl_verify, timeout=15.0) as client:
            resp = client.get(url, headers={"Authorization": f"Bearer {settings.gateway_api_key}"})
        if resp.status_code != 200:
            return Check("LLM gateway reachable", False,
                         f"{url} returned HTTP {resp.status_code}: {resp.text[:200]}"), []
        available = [m.get("id", "") for m in resp.json().get("data", [])]
        return Check("LLM gateway reachable", True,
                     f"{url} ({len(available)} models offered)"), available
    except Exception as exc:  # noqa: BLE001
        hint = "" if settings.ssl_verify is False else \
            " - if this is a TLS error behind the corporate proxy, set SSL_VERIFY=false"
        return Check("LLM gateway reachable", False, f"{url}: {exc}{hint}"), []


def report_models(settings, available: list[str]) -> list[Check]:
    """Informational only. Model routing is chosen in the settings drawer at
    runtime, so an unset role is a WARN, never a boot blocker."""
    checks: list[Check] = []
    for role, alias in settings.configured_models.items():
        if not alias:
            checks.append(Check(f"Model [{role}]", False,
                                "not selected - pick one in Settings > Model routing",
                                fatal=False))
        elif available and alias not in available:
            checks.append(Check(f"Model [{role}]", False,
                                f"{alias} is not in the gateway catalogue", fatal=False))
        else:
            checks.append(Check(f"Model [{role}]", True,
                                f"{alias} (from MODEL_{role.upper()})", fatal=False))
    return checks


def check_graph(settings) -> Check:
    from app.graph.base import probe_neo4j

    if settings.graph_backend == "kuzu":
        return Check("Knowledge graph", True, "embedded Kuzu (forced by GRAPH_BACKEND)")
    ok, detail = probe_neo4j()
    if ok:
        return Check("Knowledge graph", True, f"Neo4j reachable ({settings.neo4j_uri})")
    if settings.graph_backend == "neo4j":
        return Check("Knowledge graph", False, f"GRAPH_BACKEND=neo4j but unreachable: {detail}")
    return Check("Knowledge graph", True,
                 f"falling back to embedded Kuzu ({detail})", fatal=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Pre-flight validation")
    parser.add_argument("--skip-node", action="store_true", help="backend-only run")
    args = parser.parse_args()

    if os.name == "nt":
        os.system("")  # enable ANSI on Windows terminals

    print(f"\n{DIM}Adaptive Knowledge-to-Action Copilot - pre-flight{RESET}\n")

    checks = [check_python(), check_venv(), check_node(args.skip_node), check_env_file()]

    try:
        from app.config import get_settings
        settings = get_settings()
    except Exception as exc:  # noqa: BLE001
        checks.append(Check("Configuration valid", False, str(exc)))
        settings = None

    if settings is not None:
        checks.append(Check("Configuration valid", True,
                            f"port {settings.port}, ssl_verify={settings.ssl_verify}"))
        checks.append(check_port(settings.port))
        checks.append(check_data_dir(settings.data_dir))
        gateway_check, available = check_gateway(settings)
        checks.append(gateway_check)
        checks.extend(report_models(settings, available))
        checks.append(check_graph(settings))

        if not settings.ssl_verify:
            checks.append(Check("TLS verification", True,
                                "DISABLED - cannot distinguish the corporate proxy from a "
                                "man-in-the-middle. Synthetic data only (PRD 7.2).",
                                fatal=False))

    width = max(len(c.name) for c in checks) + 2
    for c in checks:
        print(f"  {c.marker}  {c.name.ljust(width)} {DIM}{c.detail}{RESET}")

    failures = [c for c in checks if not c.ok and c.fatal]
    warnings = [c for c in checks if not c.ok and not c.fatal]

    print()
    if failures:
        print(f"{RED}Pre-flight FAILED{RESET} - {len(failures)} blocking issue(s):")
        for c in failures:
            print(f"  - {c.name}: {c.detail}")
        print()
        return 1

    suffix = f" ({len(warnings)} warning(s))" if warnings else ""
    print(f"{GREEN}Pre-flight passed{RESET}{suffix}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
