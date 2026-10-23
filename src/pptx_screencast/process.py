"""Running ffmpeg in its own session, so a stuck process can be killed."""

import os
import signal
import subprocess


def run_proc(cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
    """Run a command in its own session and kill the whole group on a timeout.

    ffmpeg starts helper processes of its own. Killing only the parent would
    leave them holding the output file, so the session is killed as a group.
    """
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            proc.kill()
        stdout, stderr = proc.communicate()
    return subprocess.CompletedProcess(
        cmd, proc.returncode,
        stdout.decode(errors="replace"),
        stderr.decode(errors="replace"),
    )


__all__ = ["run_proc"]
