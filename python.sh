#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source "$root/env.sh"
py=${ROMKIT_LINUX_PYTHON:-python3}
"$py" -c 'import sys; assert sys.platform == "linux" and sys.version_info >= (3,12), "Linux Python 3.12+ required"'
exec "$py" -X utf8 "$@"
