"""Operator-only cgroup launcher; drops root before running project/model code."""

import argparse
import os
import pwd
import re
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--group", required=True)
    parser.add_argument("--quota-us", type=int, default=92000)
    parser.add_argument("--uid", type=int, default=1000)
    parser.add_argument("--cpu", type=int, default=0)
    parser.add_argument("--settings")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit("Operator root is required to create a scoped CPU cgroup")
    if not re.fullmatch(r"lattice-[a-z0-9-]{1,55}", args.group):
        raise SystemExit("Use a dedicated lattice-* cgroup name, without paths")
    if not 10000 <= args.quota_us <= 100000 or args.uid <= 0:
        raise SystemExit("Require 0.1-1 CPU and a non-root execution UID")
    if args.cpu not in os.sched_getaffinity(0):
        raise SystemExit("Requested CPU is unavailable")
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command or not Path(command[0]).is_absolute():
        raise SystemExit("Supply an absolute executable after --")
    account = pwd.getpwuid(args.uid)
    group = Path("/sys/fs/cgroup") / args.group
    expected = f"{args.quota_us} 100000"
    created = not group.exists()
    group.mkdir(exist_ok=True)
    cpu_max = group / "cpu.max"
    if not cpu_max.exists():
        if created:
            group.rmdir()
        raise SystemExit(
            "CPU controller is not delegated; parent configuration unchanged"
        )
    if not created and cpu_max.read_text().strip() != expected:
        raise SystemExit(
            "Existing cgroup has a different budget; refusing to change it"
        )
    cpu_max.write_text(expected + "\n")
    burst = group / "cpu.max.burst"
    if burst.exists() and burst.read_text().strip() != "0":
        raise SystemExit("Require zero CPU burst credit for reproducible limits")
    (group / "cgroup.procs").write_text(str(os.getpid()) + "\n")
    os.sched_setaffinity(0, {args.cpu})
    if args.settings:
        os.environ["LATTICE_CONFIG"] = str(Path(args.settings).resolve())
    os.initgroups(account.pw_name, account.pw_gid)
    os.setgid(account.pw_gid)
    os.setuid(account.pw_uid)
    os.execv(command[0], command)


if __name__ == "__main__":
    main()
