import argparse
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

DEFAULT_DEST = Path(__file__).resolve().parent.parent / "data" / "raw"


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def find_adb(explicit):
    exe = explicit or shutil.which("adb")
    if not exe:
        sys.exit("adb not found. Install Android platform-tools and add it to the PATH, or pass --adb.")
    return exe


def pick_device(adb, serial):
    lines = run([adb, "devices"]).stdout.splitlines()[1:]
    devices = [line.split() for line in lines if line.strip()]
    ready = [d[0] for d in devices if len(d) > 1 and d[1] == "device"]
    if any(len(d) > 1 and d[1] == "unauthorized" for d in devices):
        sys.exit("Headset is unauthorized. Put it on and accept the USB debugging prompt.")
    if serial:
        if serial not in ready:
            sys.exit(f"Device {serial} not found. Connected: {ready or 'none'}")
        return serial
    if not ready:
        sys.exit("No headset found. Connect it by USB (or adb connect) and enable developer mode.")
    if len(ready) > 1:
        sys.exit(f"Several devices connected {ready}. Pass --serial.")
    return ready[0]


def list_remote(base, remote_dir, pattern):
    res = run(base + ["shell", f"stat -c '%s %n' {remote_dir}/{pattern}"])
    files = {}
    for line in res.stdout.splitlines():
        parts = line.strip().split(" ", 1)
        if len(parts) == 2 and parts[0].isdigit():
            files[PurePosixPath(parts[1]).name] = int(parts[0])
    return files


def main():
    ap = argparse.ArgumentParser(
        description="Pull only new or changed gaze CSVs from the headset into data/raw.")
    ap.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    ap.add_argument("--remote-dir", default="/sdcard/Download")
    ap.add_argument("--pattern", default="gaze_*.csv")
    ap.add_argument("--adb", default=None, help="path to the adb executable")
    ap.add_argument("--serial", default=None, help="device serial when several are connected")
    ap.add_argument("--delete-remote", action="store_true",
                    help="delete each file from the headset after it is verified locally")
    ap.add_argument("--dry-run", action="store_true", help="show what would happen without changing anything")
    args = ap.parse_args()

    adb = find_adb(args.adb)
    serial = pick_device(adb, args.serial)
    base = [adb, "-s", serial] if args.serial else [adb]

    files = list_remote(base, args.remote_dir, args.pattern)
    if not files:
        print(f"No files matching {args.pattern} in {args.remote_dir}.")
        return

    args.dest.mkdir(parents=True, exist_ok=True)
    pulled = skipped = failed = deleted = 0

    for name, size in sorted(files.items()):
        local = args.dest / name
        up_to_date = local.exists() and local.stat().st_size == size
        ok = up_to_date

        if up_to_date:
            skipped += 1
            print(f"skip   {name} (already up to date)")
        elif args.dry_run:
            print(f"would pull {name} ({size} bytes)")
            continue
        else:
            res = run(base + ["pull", f"{args.remote_dir}/{name}", str(local)])
            ok = res.returncode == 0 and local.exists() and local.stat().st_size == size
            if ok:
                pulled += 1
                print(f"pulled {name} ({size} bytes)")
            else:
                failed += 1
                print(f"FAILED {name}: {res.stderr.strip() or 'size mismatch'}")

        if args.delete_remote and ok:
            if args.dry_run:
                print(f"would delete {name} from the headset")
            else:
                res = run(base + ["shell", f"rm '{args.remote_dir}/{name}'"])
                if res.returncode == 0:
                    deleted += 1

    print(f"Done: {pulled} pulled, {skipped} skipped, {failed} failed, {deleted} deleted from headset.")
    print(f"Destination: {args.dest}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()