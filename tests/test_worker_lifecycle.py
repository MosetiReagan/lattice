"""Real Linux process lifecycle; no model or accelerator is mocked as hardware evidence."""

import os
import subprocess
import sys
import time
from pathlib import Path


def test_worker_exits_after_parent_crashes():
    code = """import os,subprocess,sys
child=subprocess.Popen([sys.executable,'-m','lattice.worker','128',str(os.getpid()),'/bin/sleep','30'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
print(child.pid,flush=True)
os._exit(0)
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    pid = int(result.stdout.strip())
    for _ in range(100):
        path = Path(f"/proc/{pid}/status")
        if not path.exists():
            return
        try:
            if "\nState:\tZ" in path.read_text():
                return
        except FileNotFoundError:
            return
        time.sleep(0.01)
    os.kill(pid, 15)
    raise AssertionError("Worker survived parent death")
