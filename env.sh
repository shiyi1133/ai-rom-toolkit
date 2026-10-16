#!/usr/bin/env bash
# Source this file to affect this shell only; nothing is written to shell profiles.
ROMKIT_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
export ROMKIT_ROOT
export PATH="$ROMKIT_ROOT/runtime/linux/arm/bin:$ROMKIT_ROOT/runtime/linux/rgbds:$PATH"
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
