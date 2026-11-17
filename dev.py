#!/usr/bin/env python3
"""Local launcher for the three OBSIDIAN RUSSIA Python services.

Usage:
    python dev.py run
    python dev.py admin site|forum|wiki
    python dev.py backup forum|wiki

Each service uses an isolated .runtime/<name>/ SQLite directory. No third-party
packages are needed. This launcher is for local development, not production.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
SERVICES = {
    "site": ("Сайт", "server.py", "OBSIDIAN_DATA_DIR", "OBSIDIAN_PORT", 8080, "/health"),
    "forum": ("Форум", "app.py", "OBFORUM_DATA_DIR", "OBFORUM_PORT", 8090, "/health"),
    "wiki": ("Вики", "app.py", "OBWIKI_DATA_DIR", "OBWIKI_PORT", 8100, "/api/stats"),
}


def settings(name: str):
    folder, script, data_key, port_key, default_port, health_path = SERVICES[name]
    env = os.environ.copy()
    env.setdefault(data_key, str(ROOT / ".runtime" / name))
    port = int(env.get(port_key, str(default_port)))
    if not 1 <= port <= 65535:
        raise ValueError(f"Invalid port for {name}: {port}")
    return ROOT / folder, script, env, port, health_path


def wait_ready(name: str, process: subprocess.Popen, port: int, health: str) -> None:
    url = f"http://127.0.0.1:{port}{health}"
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"{name} exited with code {process.returncode}")
        try:
            with urlopen(url, timeout=0.6) as result:
                data = json.load(result)
                if result.status == 200 and (data.get("ok") is True or data.get("brand") == "OBSIDIAN RUSSIA"):
                    if process.poll() is None:
                        return
        except (URLError, OSError, ValueError, TimeoutError):
            pass
        time.sleep(0.2)
    raise RuntimeError(f"{name} did not respond at {url}")


def run_all() -> int:
    processes = []
    try:
        for name in SERVICES:
            folder, script, env, port, health = settings(name)
            proc = subprocess.Popen([sys.executable, script], cwd=folder, env=env)
            processes.append((name, proc))
            wait_ready(name, proc, port, health)
            print(f"[READY] {name}: http://127.0.0.1:{port}", flush=True)
        print("Press Ctrl+C to stop all services.", flush=True)
        while True:
            for name, proc in processes:
                if proc.poll() is not None:
                    raise RuntimeError(f"{name} stopped unexpectedly ({proc.returncode})")
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping OBSIDIAN RUSSIA...", flush=True)
        return 0
    except (RuntimeError, OSError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    finally:
        for _, proc in reversed(processes):
            if proc.poll() is None:
                proc.terminate()
        for _, proc in reversed(processes):
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


def manage(command: str, name: str) -> int:
    folder, _, env, _, _ = settings(name)
    if command == "backup" and name == "site":
        print("The site does not have a backup command; back up its SQLite database separately.", file=sys.stderr)
        return 2
    args = [sys.executable, "manage.py"]
    if name != "site":
        args.append(command)
    return subprocess.call(args, cwd=folder, env=env)


def main() -> int:
    if sys.version_info < (3, 12):
        print("Python 3.12+ is required to run all three services.", file=sys.stderr)
        return 2
    args = sys.argv[1:]
    if args == ["run"] or not args:
        return run_all()
    if len(args) == 2 and args[0] == "admin" and args[1] in SERVICES:
        return manage(*args)
    if len(args) == 2 and args[0] == "backup" and args[1] in ("forum", "wiki"):
        return manage(*args)
    print(__doc__.strip())
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
