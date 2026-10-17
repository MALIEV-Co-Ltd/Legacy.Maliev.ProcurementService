#!/usr/bin/env bash
# Temporary PR69 diagnostic only. Remove after the finding is classified.
set -euo pipefail
umask 077
scan_root=".proc69-gitleaks-scan"
test "$(git -C "$scan_root" rev-parse HEAD)" = "d6d75eec7e3b02afb4fa45d533dc35f4b71697cd"
test "$(git -C "$scan_root" rev-parse 'HEAD^{tree}')" = "6bc8d1d385c2b48fd44fabad5a65b6944e9d39b1"
test "$(git -C "$scan_root" rev-parse --is-shallow-repository)" = "true"
test "$(git -C "$scan_root" rev-list --count HEAD)" = "1"
git -C "$scan_root" diff --quiet
git -C "$scan_root" diff --cached --quiet
test -z "$(git -C "$scan_root" ls-files --others)"
for variable in GITLEAKS_CONFIG GITLEAKS_CONFIG_TOML GITLEAKS_LOG_OPTS; do
  test -z "${!variable-}"
done
python3 -B -m unittest discover -s scripts -p test_proc69_gitleaks_provenance.py
python3 -O -B -m unittest discover -s scripts -p test_proc69_gitleaks_provenance.py
private_dir="$(mktemp -d "${RUNNER_TEMP}/proc69-gitleaks-XXXXXX")"
report="$private_dir/report.json"
scan_stdout="$private_dir/stdout.log"
scan_stderr="$private_dir/stderr.log"
scanner="$private_dir/gitleaks"
cleanup() {
  status=$?
  trap - EXIT
  if ! rm -f -- "$report" "$scan_stdout" "$scan_stderr" "$scanner" 2>/dev/null; then
    printf '%s\n' 'Private diagnostic cleanup refused.' >&2
    exit 2
  fi
  if ! rmdir -- "$private_dir" 2>/dev/null; then
    printf '%s\n' 'Private diagnostic cleanup refused.' >&2
    exit 2
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
GOBIN="$private_dir" go install github.com/zricethezav/gitleaks/v8@6eaad039603a4de39fddd1cf5f727391efe9974e # v8.30.0, identical shared scanner
set +e
(
  ulimit -f 4096 || exit 2
  ulimit -t 120 || exit 2
  cd "$scan_root" || exit 2
  timeout 120s "$scanner" git --redact --exit-code 1 --report-format json --report-path "$report"
) > "$scan_stdout" 2> "$scan_stderr"
scan_status=$?
set -e
mkdir -p runner-results
set +e
python3 -B scripts/proc69_gitleaks_provenance.py "$report" "$scan_stdout" "$scan_stderr" "$scan_status" > runner-results/proc69-gitleaks-provenance.jsonl
parser_status=$?
set -e
cat runner-results/proc69-gitleaks-provenance.jsonl
if [ "$scan_status" -ne 0 ]; then
  exit "$scan_status"
fi
exit "$parser_status"
