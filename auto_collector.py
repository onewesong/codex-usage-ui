#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator

try:
    import fcntl
except ImportError:
    fcntl = None

from history_store import history_db_path


AUTO_COLLECTOR_ENV = "CODEX_USAGE_AUTO_COLLECTOR"
AUTO_COLLECTOR_INTERVAL_ENV = "CODEX_USAGE_AUTO_COLLECTOR_INTERVAL_SECONDS"
AUTO_COLLECTOR_DEFAULT_INTERVAL_SECONDS = 300
AUTO_COLLECTOR_SOURCE = "auto_collector"


def auto_collector_enabled() -> bool:
    raw_value = str(os.environ.get(AUTO_COLLECTOR_ENV, "1")).strip().lower()
    return raw_value not in {"0", "false", "no", "off"}


def auto_collector_interval_seconds() -> int:
    raw_value = os.environ.get(
        AUTO_COLLECTOR_INTERVAL_ENV,
        str(AUTO_COLLECTOR_DEFAULT_INTERVAL_SECONDS),
    )
    try:
        return max(1, int(raw_value))
    except (TypeError, ValueError):
        return AUTO_COLLECTOR_DEFAULT_INTERVAL_SECONDS


def auto_collector_runtime_dir() -> Path:
    return history_db_path().parent


def auto_collector_pid_path() -> Path:
    return auto_collector_runtime_dir() / "codex-usage-auto-collector.pid"


def auto_collector_lock_path() -> Path:
    return auto_collector_runtime_dir() / "codex-usage-auto-collector.lock"


def auto_collector_log_path() -> Path:
    return auto_collector_runtime_dir() / "codex-usage-auto-collector.log"


def auto_collector_script_path() -> Path:
    return Path(__file__).with_name("collect_history.py")


@contextmanager
def auto_collector_start_lock() -> Iterator[None]:
    lock_path = auto_collector_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as handle:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def read_auto_collector_pid() -> int | None:
    pid_path = auto_collector_pid_path()
    if not pid_path.exists():
        return None
    try:
        return int(pid_path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def write_auto_collector_pid(pid: int) -> None:
    auto_collector_pid_path().write_text(str(pid), encoding="utf-8")


def is_process_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    proc_stat_path = Path(f"/proc/{pid}/stat")
    if proc_stat_path.exists():
        try:
            proc_state = proc_stat_path.read_text(encoding="utf-8").split()[2]
        except (OSError, IndexError):
            proc_state = None
        if proc_state == "Z":
            return False
    return True


def auto_collector_status() -> Dict[str, Any]:
    pid = read_auto_collector_pid()
    running = bool(pid and is_process_running(pid))
    return {
        "enabled": auto_collector_enabled(),
        "interval_seconds": auto_collector_interval_seconds(),
        "state": "running" if running else "stopped",
        "pid": pid if running else None,
        "log_path": str(auto_collector_log_path()),
        "source": AUTO_COLLECTOR_SOURCE,
        "error": None,
    }


def ensure_auto_collector_running() -> Dict[str, Any]:
    status = auto_collector_status()
    if not status["enabled"]:
        status["state"] = "disabled"
        status["pid"] = None
        return status

    runtime_dir = auto_collector_runtime_dir()
    runtime_dir.mkdir(parents=True, exist_ok=True)

    with auto_collector_start_lock():
        status = auto_collector_status()
        if status["state"] == "running":
            return status

        pid_path = auto_collector_pid_path()
        if pid_path.exists():
            pid_path.unlink(missing_ok=True)

        command = [
            sys.executable,
            str(auto_collector_script_path()),
            "--interval-seconds",
            str(status["interval_seconds"]),
            "--source",
            AUTO_COLLECTOR_SOURCE,
        ]

        try:
            with auto_collector_log_path().open("ab") as log_handle:
                process = subprocess.Popen(
                    command,
                    cwd=str(Path(__file__).parent),
                    env={**os.environ, AUTO_COLLECTOR_ENV: "0", "PYTHONUNBUFFERED": "1"},
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
        except OSError as exc:
            status["state"] = "error"
            status["error"] = str(exc)
            return status

        write_auto_collector_pid(process.pid)
        status["state"] = "running"
        status["pid"] = process.pid
        return status


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ensure the auto collector is running.")
    parser.add_argument(
        "--status",
        action="store_true",
        help="print current collector status instead of starting it",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    status = auto_collector_status() if args.status else ensure_auto_collector_running()
    if status.get("state") == "error":
        raise SystemExit(str(status.get("error") or "failed to start auto collector"))
    print(
        f"{status.get('state')} "
        f"pid={status.get('pid') or '-'} "
        f"interval={status.get('interval_seconds')} "
        f"log={status.get('log_path')}"
    )


if __name__ == "__main__":
    main()
