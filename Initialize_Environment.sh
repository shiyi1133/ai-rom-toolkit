#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cache="$root/.cache/linux"
skip=0
while (($#)); do
  case "$1" in
    --cache-dir) [[ $# -ge 2 ]] || { echo 'Missing --cache-dir value' >&2; exit 2; }; cache=$2; shift 2 ;;
    --skip-self-test) skip=1; shift ;;
    -h|--help) echo 'Usage: bash Initialize_Environment.sh [--cache-dir DIR] [--skip-self-test]'; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done
py=${ROMKIT_LINUX_PYTHON:-python3}
"$py" -c 'import sys; sys.path.insert(0, sys.argv[1]); from toolkit_host import require_supported_host; assert require_supported_host() == "linux", "Use Initialize_Environment.ps1 on Windows"' "$root/tools"
# Resolve relative caches against the caller, before changing the working directory.
cache=$("$py" -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).resolve())' "$cache")
cd -- "$root"
"$py" -X utf8 tools/bootstrap_environment.py --cache-dir "$cache"
mkdir -p reports
run=$("$py" -c 'import uuid; print(uuid.uuid4().hex)')
"$py" -X utf8 tools/check_environment.py --report "reports/environment_linux_$run.json"
if ((skip == 0)); then
  "$py" -X utf8 tools/self_test.py --report "reports/self_test_linux_$run.json"
else
  echo 'Self-test skipped; no new self-test pass claimed.'
fi
echo "Linux core environment ready. Reports: $root/reports (run $run). Optional custom backend: not_available."
