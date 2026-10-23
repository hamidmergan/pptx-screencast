"""Subprocess tracking, so a cancelled run kills its ffmpeg processes at once."""

import os
import signal
import subprocess
import threading

_run_procs: dict[str, list[subprocess.Popen]] = {}
_run_procs_lock = threading.Lock()


def _register_proc(run_id: str, proc: subprocess.Popen) -> None:
    with _run_procs_lock:
        _run_procs.setdefault(run_id, []).append(proc)


def _unregister_proc(run_id: str, proc: subprocess.Popen) -> None:
    with _run_procs_lock:
        procs = _run_procs.get(run_id, [])
        try:
            procs.remove(proc)
        except ValueError:
            pass


def kill_run_procs(run_id: str) -> None:
    """Kill every ffmpeg process of this run, as a whole process group."""
    with _run_procs_lock:
        procs = _run_procs.pop(run_id, [])
    for proc in procs:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def run_proc(cmd: list[str], timeout: int, run_id: str | None = None) -> subprocess.CompletedProcess:
    """Run a command in its own session, so it can be killed as a group."""
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    if run_id:
        _register_proc(run_id, proc)
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            proc.kill()
        stdout, stderr = proc.communicate()
    finally:
        if run_id:
            _unregister_proc(run_id, proc)
    return subprocess.CompletedProcess(
        cmd, proc.returncode,
        stdout.decode(errors="replace"),
        stderr.decode(errors="replace"),
    )
