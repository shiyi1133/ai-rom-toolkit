#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source "$root/env.sh"
cd -- "$root"
echo 'Local Linux Arm/RGBDS are on this shell PATH. Use ./python.sh. Exit closes this shell.'
exec bash --noprofile --norc -i
