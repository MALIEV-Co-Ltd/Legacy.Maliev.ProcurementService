"""Temporary PR61 provenance projection; never emit raw scanner evidence."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

ROOT = Path(__file__).resolve().parents[1]
SCOPE = ROOT / "scripts/proc61-gitleaks-provenance-scope.json"
SCOPE_SHA256 = "1cd1ab1537591af9523aac884bf8339c02bbe089cfb40e9d1c4bd655287bdc59"
SCAN_COMMIT = "54ac1012748ba3ab0c68e51511eca081cbcf1e70"
SCAN_TREE = "8dd9aa295804cb68ab4ad97f67839552328b3166"
PR_HEAD = "b40d4dfb037ca587dde126430458520868f6b48a"
MAX_SOURCE_BYTES = 1024 * 1024
MAX_PRIVATE_BYTES = 4 * 1024 * 1024
MAX_FINDINGS = 1000
GRANTS = {"deployment":False, "financialExecution":False, "credentialRotation":False,
          "gateWaiver":False, "refMutation":False}


def require(value):
    if not value:
        raise ValueError("Provenance diagnostic refused")


def bounded_read(path, maximum, private=False, allow_empty=False):
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as stream:
        metadata = os.fstat(stream.fileno())
        require(stat.S_ISREG(metadata.st_mode))
        if private:
            require(stat.S_IMODE(metadata.st_mode) & 0o077 == 0)
        raw = stream.read(maximum + 1)
    require((allow_empty or bool(raw)) and len(raw) <= maximum)
    return raw


def object_json(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value)
            value[key] = item
        return value
    def constant(_):
        raise ValueError("Provenance diagnostic refused")
    return json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=pairs,
                      parse_constant=constant)


def safe_path(name):
    return (isinstance(name, str) and len(name) <= 512
            and re.fullmatch(r"[A-Za-z0-9_./ -]+", name) is not None
            and all(part not in ("", ".", "..") for part in name.split("/")))


def reviewed_scope():
    raw = bounded_read(SCOPE, MAX_SOURCE_BYTES)
    require(hashlib.sha256(raw).hexdigest() == SCOPE_SHA256)
    manifest = object_json(raw)
    require(isinstance(manifest, dict) and manifest["schemaVersion"] == 1
            and manifest["repository"] == "MALIEV-Co-Ltd/Legacy.Maliev.ProcurementService"
            and manifest["scanCommit"] == SCAN_COMMIT and manifest["scanTree"] == SCAN_TREE
            and manifest["associatedPrHead"] == PR_HEAD and manifest["grants"] == GRANTS)
    rows = manifest["inventory"]
    require(isinstance(rows, list) and manifest["pathCount"] == len(rows) == 242)
    paths = set()
    for row in rows:
        require(isinstance(row, dict) and set(row) == {"path", "metadata"}
                and safe_path(row["path"]) and row["path"] not in paths
                and isinstance(row["metadata"], str)
                and re.fullmatch(r"(?:100644|100755|120000) blob [0-9a-f]{40}", row["metadata"]) is not None)
        paths.add(row["path"])
    return frozenset(paths), frozenset((SCAN_COMMIT,))


def safe_provenance(data, allowed_paths, allowed_commits, exit_code):
    findings = object_json(data)
    require(isinstance(findings, list) and len(findings) <= MAX_FINDINGS
            and type(exit_code) is int and exit_code in (0, 1)
            and (bool(findings) == (exit_code == 1)))
    rows = []
    for finding in findings:
        require(isinstance(finding, dict))
        rule, name, line, commit = (finding.get(key) for key in ("RuleID", "File", "StartLine", "Commit"))
        require(isinstance(rule, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", rule) is not None)
        require(safe_path(name) and name in allowed_paths)
        require(type(line) is int and 1 <= line <= 10000000)
        require(isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit) is not None
                and commit in allowed_commits)
        rows.append({"RuleID":rule, "File":name, "StartLine":line, "Commit":commit})
    # Nothing is emitted until the complete report has passed every check.
    return rows


def private_rows(report, stdout, stderr, exit_code):
    paths = (report, stdout, stderr)
    require(tuple(path.name for path in paths) == ("report.json", "stdout.log", "stderr.log")
            and len({path.parent for path in paths}) == 1)
    parent = report.parent
    metadata = parent.lstat()
    require(stat.S_ISDIR(metadata.st_mode) and stat.S_IMODE(metadata.st_mode) & 0o077 == 0
            and parent.name.startswith("proc61-gitleaks-")
            and parent.parent.resolve() == Path(os.environ["RUNNER_TEMP"]).resolve())
    # Check every actual private sink before decoding or projecting any finding.
    raw = bounded_read(report, MAX_PRIVATE_BYTES, private=True)
    bounded_read(stdout, MAX_PRIVATE_BYTES, private=True, allow_empty=True)
    bounded_read(stderr, MAX_PRIVATE_BYTES, private=True, allow_empty=True)
    allowed_paths, allowed_commits = reviewed_scope()
    return safe_provenance(raw, allowed_paths, allowed_commits, exit_code)


def main(arguments):
    try:
        require(len(arguments) == 4)
        report, stdout, stderr = map(Path, arguments[:3])
        rows = private_rows(report, stdout, stderr, int(arguments[3]))
        for row in rows:
            print(json.dumps(row, sort_keys=True))
        return 0
    except (ValueError, OSError, UnicodeError, TypeError, KeyError, OverflowError, RecursionError):
        print("Gitleaks provenance diagnostic refused.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
