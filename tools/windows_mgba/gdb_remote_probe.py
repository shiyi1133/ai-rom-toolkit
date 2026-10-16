"""Minimal read-only probe for an mGBA GDB remote stub."""

from __future__ import annotations

import argparse
import json
import socket
from pathlib import Path


def packet(payload: bytes) -> bytes:
    return b"$" + payload + b"#" + f"{sum(payload) & 0xFF:02x}".encode("ascii")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("session", type=Path)
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()
    session = json.loads(args.session.read_text(encoding="utf-8"))
    if session.get("mode") != "gdb" or not session.get("gdb_port"):
        raise SystemExit("session is not a GDB-mode instance")
    with socket.create_connection((session["host"], int(session["gdb_port"])), args.timeout) as sock:
        sock.settimeout(args.timeout)
        sock.sendall(packet(b"?"))
        response = bytearray()
        while b"#" not in response:
            response.extend(sock.recv(4096))
    if b"$" not in response or b"#" not in response:
        raise SystemExit(f"invalid GDB remote response: {response!r}")
    print(bytes(response).decode("ascii", errors="replace"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
