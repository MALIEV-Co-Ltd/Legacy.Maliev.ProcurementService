"""Hosted-only resource admission. Never start a worker or stop an uncertain process."""
import datetime
import json
import os
import pathlib
import re
import sys

MIN_AVAILABLE_KIB = 3145728
MAX_MEMINFO_BYTES = 65536
MAX_PROC_ENTRIES = 16384
MAX_PROC_BYTES = 4096
WORKERS = {"dotnet", "testhost", "MSBuild", "VBCSCompiler"}


def require(value, message):
    if not value:
        raise ValueError(message)


def bounded(path, maximum):
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    require(0 < len(raw) <= maximum, "Admission input exceeds actual bound")
    return raw


def memory_available(raw):
    text = raw.decode("ascii", errors="strict")
    matches = re.findall(r"^MemAvailable:\s+([0-9]+) kB$", text, re.MULTILINE)
    require(len(matches) == 1, "Exactly one MemAvailable observation required")
    value = int(matches[0])
    require(value >= MIN_AVAILABLE_KIB, "Resource admission blocked: MemAvailable below3145728KiB")
    return value


def worker_inventory(proc):
    workers, count = [], 0
    for path in proc.iterdir():
        if not path.name.isdecimal():
            continue
        count += 1
        require(count <= MAX_PROC_ENTRIES, "Process observation bound exhausted")
        try:
            name = bounded(path / "comm", MAX_PROC_BYTES).decode("utf-8", errors="strict").strip()
            if name not in WORKERS:
                continue
            stat = bounded(path / "stat", MAX_PROC_BYTES).decode("utf-8", errors="strict")
            fields = stat[stat.rfind(")") + 2:].split()
            require(len(fields) >= 20 and fields[19].isdecimal(), "Worker start identity unavailable")
            workers.append({"pid": int(path.name), "executableName": name, "startTicks": int(fields[19]),
                            "owner": "uncertain-preserved"})
        except FileNotFoundError:
            # A process that exited during this read cannot become our worker.
            continue
    return workers


def admit(output, stage, proc=pathlib.Path("/proc")):
    require(os.environ.get("GITHUB_ACTIONS") == "true" and bool(os.environ.get("GITHUB_RUN_ID"))
            and bool(os.environ.get("GITHUB_RUN_ATTEMPT")), "Hosted run custody required")
    require(stage in {"initial", "baseline-build", "baseline-test", "candidate-build", "candidate-test"},
            "Unknown bounded admission stage")
    receipt = {"stage": stage, "owningRun": os.environ["GITHUB_RUN_ID"],
               "owningAttempt": os.environ["GITHUB_RUN_ATTEMPT"],
               "observedAtUtc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "minimumMemAvailableKiB": MIN_AVAILABLE_KIB, "passed": False, "workers": [],
               "policy": "No guard override, no worker started, no process terminated"}
    try:
        receipt["memAvailableKiB"] = memory_available(bounded(proc / "meminfo", MAX_MEMINFO_BYTES))
        receipt["workers"] = worker_inventory(proc)
        require(not receipt["workers"], "Competing build/test worker observed; preserve and stop admission")
        receipt["passed"] = True
        return receipt
    except BaseException as error:
        receipt["failureCategory"] = type(error).__name__
        raise
    finally:
        output.mkdir(parents=True, exist_ok=True)
        target = output / ("admission-" + stage + ".json")
        require(not target.exists(), "Admission evidence must not be overwritten")
        target.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    admit(pathlib.Path(sys.argv[1]), sys.argv[2])
