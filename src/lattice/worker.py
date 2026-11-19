"""Apply worker limits in a fresh interpreter, then exec without a shell.

Avoids preexec_fn: the parent may already have hash-check or HTTP threads.
"""

import ctypes
import os
import resource
import signal
import sys


def main() -> None:
    limit = int(sys.argv[1]) * 1024**2
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    parent_pid = int(sys.argv[2])
    # Linux parent-death signal survives exec of the non-setuid native worker.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGTERM, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "Cannot establish worker parent-death signal")
    if os.getppid() != parent_pid:
        raise SystemExit("Parent exited before worker startup")
    os.execv(sys.argv[3], sys.argv[3:])


if __name__ == "__main__":
    main()
