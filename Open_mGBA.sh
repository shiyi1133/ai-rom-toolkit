#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
image="$root/runtime/linux/mgba/mgba.AppImage"
[[ -x "$image" ]] || { echo 'Run Initialize_Environment.sh first.' >&2; exit 1; }
if [[ -z ${DISPLAY:-} && -z ${WAYLAND_DISPLAY:-} ]]; then
  echo 'No graphical display. Toolchain/self-tests remain usable; GUI gameplay was not tested.' >&2
  exit 1
fi
# Isolate personal settings; pass only ROM/SAV copies from your project runtime.
mkdir -p "$root/workspace/runtime/mgba-linux/config" "$root/workspace/runtime/mgba-linux/cache"
export XDG_CONFIG_HOME="$root/workspace/runtime/mgba-linux/config"
export XDG_CACHE_HOME="$root/workspace/runtime/mgba-linux/cache"
exec "$image" --appimage-extract-and-run "$@"
